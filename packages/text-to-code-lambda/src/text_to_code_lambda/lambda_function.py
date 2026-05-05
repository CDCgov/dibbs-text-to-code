import io
import json
import os
from datetime import UTC
from datetime import datetime

from aws_lambda_powertools import Logger
from aws_lambda_powertools.utilities.data_classes import SQSEvent
from aws_lambda_powertools.utilities.data_classes import SQSRecord
from aws_lambda_powertools.utilities.data_classes import event_source
from aws_lambda_powertools.utilities.typing import LambdaContext
from botocore.client import BaseClient
from opensearchpy import OpenSearch

import lambda_handler
from shared_models import Code
from shared_models import NonstandardCodeInstance
from text_to_code.models import Candidate
from text_to_code.models import SchematronErrorDetail
from text_to_code.models import query as query_models
from text_to_code.services import eicr_processor
from text_to_code.services import evaluator
from text_to_code.services import schematron_processor
from text_to_code.services.embedder import embed
from text_to_code.services.query import QueryBuilder
from text_to_code.services.reranker import rerank

# Initialize the logger
logger = Logger(service="ttc")

# Environment variables
SCHEMATRON_ERROR_PREFIX = os.getenv("SCHEMATRON_ERROR_PREFIX", "ValidationResponseV2/")
TTC_INPUT_PREFIX = os.getenv("TTC_INPUT_PREFIX", "TextToCodeSubmissionV2/")
TTC_OUTPUT_PREFIX = os.getenv("TTC_OUTPUT_PREFIX", "TTCAugmentationMetadataV2/")
TTC_METADATA_PREFIX = os.getenv("TTC_METADATA_PREFIX", "TTCMetadataV2/")
AWS_REGION = os.getenv("AWS_REGION")
S3_ENDPOINT_URL = os.getenv("S3_ENDPOINT_URL")
OPENSEARCH_ENDPOINT_URL = os.getenv("OPENSEARCH_ENDPOINT_URL")
OPENSEARCH_INDEX = os.getenv("OPENSEARCH_INDEX", "ttc-index")

# Constants
NO_DATA_FIELDS_MESSAGE = (
    "No relevant data fields identified from Schematron errors for TTC processing"
)


@event_source(data_class=SQSEvent)
@logger.inject_lambda_context
def handler(event: SQSEvent, context: LambdaContext) -> dict:
    """Text to Code lambda entry point.

    :param event: The SQS event containing the S3 event data for processing.
    :param context: The Lambda context object.
    :return: A dictionary containing the status code, message, and any relevant data about the processing results.
    """
    auth = lambda_handler.create_aws_auth()
    opensearch_client = lambda_handler.create_opensearch_client(auth)
    s3_client = lambda_handler.create_s3_client()

    logger.info("Received event", record_count=len(event["Records"]), status="processing")

    failures = []
    successes = []

    for record in event.records:
        try:
            process_record(record, s3_client, opensearch_client)
            successes.append(record.message_id)
        except Exception as e:
            logger.exception(
                "Error processing record",
                message_id=record.message_id,
                status="error",
            )
            failures.append({"message_id": record.message_id, "error": str(e)})

    result = (
        {
            "statusCode": 200,
            "message": "TTC processed with some failures!",
            "failures": failures,
            "num_failure_eicrs": len(failures),
            "num_success_eicrs": len(successes),
        }
        if failures
        else {
            "statusCode": 200,
            "message": "TTC processed successfully!",
            "num_success_eicrs": len(successes),
        }
    )

    logger.info(
        "TTC invocation completed",
        status="partial_failure" if failures else "success",
        num_failure_eicrs=len(failures),
        num_success_eicrs=len(successes),
    )

    return result


def process_record(record: SQSRecord, s3_client: BaseClient, opensearch_client: OpenSearch) -> None:
    """Process each SQS record.

    :param record: The SQS record to process
    """
    if not record.body:
        logger.warning("Empty SQS body", message_id=record.message_id, status="skipped")
        return

    s3_event = json.loads(record.body)

    # Parse the EventBridge S3 event from the SQS message body
    eventbridge_data = lambda_handler.get_eventbridge_data_from_s3_event(s3_event)
    object_key = eventbridge_data["object_key"]
    bucket_name = eventbridge_data.get("bucket_name")

    if not bucket_name:
        raise ValueError(
            "No bucket name found in S3 event payload. "
            "The TTC lambda derives its target bucket from the event and does not use a "
            "static bucket configuration. Ensure the EventBridge/S3 event includes "
            "detail.bucket.name."
        )

    # Extract persistence_id from the RR object key
    persistence_id = lambda_handler.get_persistence_id(object_key, TTC_INPUT_PREFIX)

    with logger.append_context_keys(
        persistence_id=persistence_id,
        bucket_name=bucket_name,
        trigger_s3_key=object_key,
    ):
        logger.info("Processing TTC event", status="processing")
        _process_record_pipeline(persistence_id, s3_client, opensearch_client, bucket_name)


def _initialize_ttc_outputs(persistence_id: str) -> tuple[dict, dict]:
    """Initialize TTC output and metadata output dictionaries.

    :param persistence_id: The persistence ID extracted from the S3 object key
    :return: The TTC output and TTC metadata output dictionaries.
    """
    ttc_output: dict = {
        "persistence_id": "",
        "eicr_metadata": {},
        "schematron_errors": {},
        "unmatched_schematron_errors": {},
    }
    ttc_metadata_output: dict = {
        "persistence_id": "",
        "eicr_metadata": {},
        "schematron_errors": {},
        "processed_at": "",
    }
    ttc_output["persistence_id"] = persistence_id
    ttc_metadata_output["persistence_id"] = persistence_id
    ttc_metadata_output["processed_at"] = datetime.now(UTC).isoformat()
    return ttc_output, ttc_metadata_output


def _load_schematron_data_fields(
    persistence_id: str, s3_client: BaseClient, bucket_name: str
) -> list:
    """Load Schematron errors from S3 and extract relevant fields.

    :param persistence_id: The persistence ID extracted from the S3 object key
    :param s3_client: The S3 client to use for fetching files.
    :param bucket_name: The S3 bucket name to read from.
    :return: The relevant Schematron data fields for TTC processing.
    """
    object_key = f"{SCHEMATRON_ERROR_PREFIX}{persistence_id}"
    logger.info(
        "Loading Schematron errors",
        bucket_name=bucket_name,
        s3_key=object_key,
        status="processing",
    )
    schematron_errors = lambda_handler.get_file_content_from_s3(
        bucket_name=bucket_name,
        object_key=object_key,
        s3_client=s3_client,
    )

    # Process Schematron errors to identify relevant data fields for TTC processing
    logger.info("Extracting relevant fields", status="processing")
    return schematron_processor.get_data_fields_from_schematron_error(schematron_errors)


def _load_original_eicr(persistence_id: str, s3_client: BaseClient, bucket_name: str) -> str:
    """Load the original eICR from S3.

    :param persistence_id: The persistence ID extracted from the S3 object key
    :param s3_client: The S3 client to use for fetching files.
    :param bucket_name: The S3 bucket name to read from.
    :return: The original eICR content.
    """
    object_key = f"{TTC_INPUT_PREFIX}{persistence_id}"
    logger.info(
        "Retrieving eICR from S3",
        bucket_name=bucket_name,
        s3_key=object_key,
        status="processing",
    )
    original_eicr_content = lambda_handler.get_file_content_from_s3(
        bucket_name=bucket_name, object_key=object_key, s3_client=s3_client
    )
    logger.info("Retrieved eICR content", status="success")
    return original_eicr_content


def _populate_eicr_metadata(
    processor: eicr_processor.EicrProcessor,
    ttc_output: dict,
    ttc_metadata_output: dict,
) -> None:
    """Populate eICR metadata on TTC outputs.

    :param processor: The initialized EICR processor.
    :param ttc_output: The TTC output dictionary.
    :param ttc_metadata_output: The TTC metadata output dictionary.
    """
    # # Process the eICR for TTC
    # Retrieve eICR Metadata
    eicr_metadata = processor.eicr_metadata

    ttc_output["eicr_metadata"] = eicr_metadata
    ttc_metadata_output["eicr_metadata"] = eicr_metadata


def _build_nonstandard_code_instance(
    schematron_error: SchematronErrorDetail,
    new_translation: Code,
    selected_candidate: Candidate,
) -> NonstandardCodeInstance:
    """Build a NonstandardCodeInstance object for the TTC output.

    :param schematron_error: The Schematron error being processed.
    :param new_translation: The new translation retrieved from OpenSearch for the error.
    :param selected_candidate: The text candidate that was selected as the most relevant for the error.
    :return: A NonstandardCodeInstance object populated with the relevant information.
    """
    new_translation_with_text = new_translation.model_copy(
        update={"original_text": selected_candidate.value}
    )
    return NonstandardCodeInstance(
        schematron_error=schematron_error.error_message,
        schematron_error_xpath=schematron_error.error_context,
        field_type=schematron_error.field,
        new_translation=new_translation_with_text,
    )


def _process_schematron_errors(
    processor: eicr_processor.EicrProcessor,
    schematron_data_fields: list,
    opensearch_client: OpenSearch,
    ttc_output: dict,
    ttc_metadata_output: dict,
) -> None:
    """Process Schematron errors for TTC.

    :param processor: The initialized EICR processor.
    :param schematron_data_fields: The relevant Schematron data fields for TTC processing.
    :param opensearch_client: The OpenSearch client.
    :param ttc_output: The TTC output dictionary.
    :param ttc_metadata_output: The TTC metadata output dictionary.
    """
    # Evaluate candidates and select relevant text for each error in the eICR
    for error in schematron_data_fields:
        data_field = error.field
        criteria = evaluator.get_evaluation_criteria_for_data_field(data_field)

        if data_field not in ttc_output["schematron_errors"]:
            ttc_output["schematron_errors"][data_field] = []
        if data_field not in ttc_output["unmatched_schematron_errors"]:
            ttc_output["unmatched_schematron_errors"][data_field] = []
        if data_field not in ttc_metadata_output["schematron_errors"]:
            ttc_metadata_output["schematron_errors"][data_field] = []

        text_candidates = processor.get_text_candidates(error.error_context, data_field)

        logger.info(
            "Evaluating candidates and selecting relevant text for each error in the eICR",
            status="processing",
        )

        selected_candidate = evaluator.select_relevant_text(
            candidates=text_candidates, criteria=criteria
        )

        error.candidate = selected_candidate

        logger.info(
            "Embedding the relevant text strings for each error in the eICR",
            status="processing",
        )

        if selected_candidate is None:
            unmatched_error = error.model_dump()
            unmatched_error["reason"] = "No relevant text candidate was selected"
            ttc_output["unmatched_schematron_errors"][data_field].append(unmatched_error)

            metadata_error = error.model_dump()
            metadata_error["reason"] = "No relevant text candidate was selected"
            ttc_metadata_output["schematron_errors"][data_field].append(metadata_error)
            continue

        vector_embedding = embed(selected_candidate.value)

        vector_parameters = query_models.VectorSearchParams(
            vector=vector_embedding.tolist(), data_field=data_field
        )

        logger.info(
            "Querying OpenSearch with the relevant text strings and retrieving code suggestions",
            status="processing",
        )
        query = QueryBuilder().with_vector_search(vector_parameters).build()

        opensearch_retrieved_scores = lambda_handler.retrieve_opensearch_results(
            query=query, index=OPENSEARCH_INDEX, opensearch_client=opensearch_client
        )

        # The OpenSearch results object has a couple levels of nesting,
        # but all we care about for reranking is extracting the actual
        # text strings of the ANN LOINC codes
        results_list = opensearch_retrieved_scores.hits.hits
        retrieved_loinc_names = [hit.source.description for hit in results_list]
        ranked_results = rerank(selected_candidate.value, retrieved_loinc_names)

        if results_list:
            ttc_output["schematron_errors"][data_field].append(
                _build_nonstandard_code_instance(
                    schematron_error=error,
                    new_translation=Code(
                        code=results_list[0].source.loinc_code,
                        code_system="2.16.840.1.113883.6.1",
                        code_system_name="LOINC",
                        display_name=results_list[0].source.description,
                    ),
                    selected_candidate=selected_candidate,
                ).model_dump()
            )
        else:
            # TODO: Shape of this output could change depending on needs of the Augmentation Lambda
            unmatched_error = error.model_dump()
            unmatched_error["reason"] = (
                "Selected candidate found, but no OpenSearch code match was returned"
            )
            ttc_output["unmatched_schematron_errors"][data_field].append(unmatched_error)

        metadata_error = error.model_dump()
        metadata_error["opensearch_retrieved_scores"] = opensearch_retrieved_scores
        metadata_error["reranker_processed_results"] = ranked_results
        if not results_list:
            metadata_error["reason"] = (
                "Selected candidate found, but no OpenSearch code match was returned"
            )
        ttc_metadata_output["schematron_errors"][data_field].append(metadata_error)


def _save_ttc_metadata_output(
    persistence_id: str,
    ttc_metadata_output: dict,
    s3_client: BaseClient,
    bucket_name: str,
) -> None:
    """Save TTC metadata output to S3.

    :param persistence_id: The persistence ID extracted from the S3 object key
    :param ttc_metadata_output: The TTC metadata output dictionary.
    :param s3_client: The S3 client to use for uploading files.
    :param bucket_name: The S3 bucket name to write to.
    """
    metadata_key = f"{TTC_METADATA_PREFIX}{persistence_id.removesuffix('.xml')}.json"

    logger.info(
        "Saving TTC metadata output to S3",
        bucket_name=bucket_name,
        s3_key=metadata_key,
        status="processing",
    )
    lambda_handler.put_file(
        file_obj=io.BytesIO(json.dumps(ttc_metadata_output, default=str).encode("utf-8")),
        bucket_name=bucket_name,
        object_key=metadata_key,
        s3_client=s3_client,
    )
    logger.info(
        "Saved TTC metadata output to S3",
        bucket_name=bucket_name,
        s3_key=metadata_key,
        status="success",
    )


def _save_ttc_outputs(
    persistence_id: str,
    ttc_output: dict,
    ttc_metadata_output: dict,
    s3_client: BaseClient,
    bucket_name: str,
) -> None:
    """Save TTC output and metadata output to S3.

    :param persistence_id: The persistence ID extracted from the S3 object key
    :param ttc_output: The TTC output dictionary.
    :param ttc_metadata_output: The TTC metadata output dictionary.
    :param s3_client: The S3 client to use for uploading files.
    :param bucket_name: The S3 bucket name to write to.
    """
    # Save the TTC output to S3 for the Augmentation Lambda to consume
    logger.info(
        "Saving TTC output to S3",
        bucket_name=bucket_name,
        s3_key=f"{TTC_OUTPUT_PREFIX}{persistence_id}",
        status="processing",
    )
    lambda_handler.put_file(
        file_obj=io.BytesIO(json.dumps(ttc_output, default=str).encode("utf-8")),
        bucket_name=bucket_name,
        object_key=f"{TTC_OUTPUT_PREFIX}{persistence_id}",
        s3_client=s3_client,
    )
    logger.info(
        "Saved TTC output to S3",
        bucket_name=bucket_name,
        s3_key=f"{TTC_OUTPUT_PREFIX}{persistence_id}",
        status="success",
    )

    # Save the TTC metadata output for completing model evaluation and analysis of TTC results
    _save_ttc_metadata_output(persistence_id, ttc_metadata_output, s3_client, bucket_name)


def _process_record_pipeline(
    persistence_id: str,
    s3_client: BaseClient,
    opensearch_client: OpenSearch,
    bucket_name: str,
) -> dict:
    """The main pipeline for processing each record.

    The pipeline includes:
    - Retrieving Schematron errors from S3.
    - Extracting relevant data fields from the Schematron errors for TTC processing
    - Retrieving the original eICR from S3
    - Processing the eICR for TTC, which includes:
        - Evaluating candidates and selecting relevant text for each error in the eICR
        - Embedding the relevant text string for each error in the eICR
        - Querying OpenSearch with the relevant text string and retrieving the code suggestions
        - Reranking the code suggestions based on relevance to the error and returning the top suggestion
        - Creating the output to pass to the Augmentation Lambda and saving it to S3
        - Creating the metadata object to save in S3 for analysis of TTC results

    :param persistence_id: The persistence ID extracted from the S3 object key
    :param s3_client: The S3 client to use for S3 operations.
    :param opensearch_client: The OpenSearch client.
    :param bucket_name: The S3 bucket name extracted from the triggering event.
    """
    ttc_output, ttc_metadata_output = _initialize_ttc_outputs(persistence_id)

    logger.info("Starting TTC processing", status="processing")
    schematron_data_fields = _load_schematron_data_fields(persistence_id, s3_client, bucket_name)

    if not schematron_data_fields:
        logger.warning(
            "No data fields found from Schematron errors for TTC processing",
            status="skipped",
        )
        ttc_output["message"] = NO_DATA_FIELDS_MESSAGE
        ttc_metadata_output["reason_for_skipping"] = NO_DATA_FIELDS_MESSAGE
        _save_ttc_metadata_output(persistence_id, ttc_metadata_output, s3_client, bucket_name)
        logger.info("TTC processing completed", status="no_matches_found")
        return {
            "statusCode": 200,
            "message": "TTC processed successfully, but no relevant candidates or code matches were found.",
            "result": "no_matches_found",
        }

    original_eicr_content = _load_original_eicr(persistence_id, s3_client, bucket_name)
    processor = eicr_processor.EicrProcessor(original_eicr_content)
    _populate_eicr_metadata(processor, ttc_output, ttc_metadata_output)
    _process_schematron_errors(
        processor,
        schematron_data_fields,
        opensearch_client,
        ttc_output,
        ttc_metadata_output,
    )
    _save_ttc_outputs(persistence_id, ttc_output, ttc_metadata_output, s3_client, bucket_name)

    has_matches = any(len(matches) > 0 for matches in ttc_output["schematron_errors"].values())

    if not has_matches:
        logger.info("TTC processing completed", status="no_matches_found")
        return {
            "statusCode": 200,
            "message": "TTC processed successfully, but no relevant candidates or code matches were found.",
            "result": "no_matches_found",
        }

    logger.info("TTC processing completed", status="matched")
    return {
        "statusCode": 200,
        "message": "TTC processed successfully with matches.",
        "result": "matched",
    }
