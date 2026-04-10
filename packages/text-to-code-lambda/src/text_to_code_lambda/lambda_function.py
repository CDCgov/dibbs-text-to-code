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
from shared_models import EICR_INPUT_PREFIX
from shared_models import S3_BUCKET
from shared_models import SCHEMATRON_ERROR_PREFIX
from shared_models import TTC_INPUT_PREFIX
from shared_models import TTC_METADATA_PREFIX
from shared_models import TTC_OUTPUT_PREFIX
from shared_models import Code
from shared_models import SchematronErrorDetail
from shared_models import TTCOutput
from text_to_code.models import query as query_models
from text_to_code.models.eicr import TTCMetadata
from text_to_code.services import eicr_processor
from text_to_code.services import embedder
from text_to_code.services import evaluator
from text_to_code.services import reranker
from text_to_code.services import schematron_processor
from text_to_code.services.eicr_processor import EicrProcessor
from text_to_code.services.query import QueryBuilder

# Initialize the logger
logger = Logger(service="ttc")

# Environment variables
_EICR_INPUT_PREFIX = os.getenv("EICR_INPUT_PREFIX", EICR_INPUT_PREFIX)
_S3_BUCKET = os.getenv("S3_BUCKET", S3_BUCKET)
_SCHEMATRON_ERROR_PREFIX = os.getenv("SCHEMATRON_ERROR_PREFIX", SCHEMATRON_ERROR_PREFIX)
_TTC_INPUT_PREFIX = os.getenv("TTC_INPUT_PREFIX", TTC_INPUT_PREFIX)
_TTC_METADATA_PREFIX = os.getenv("TTC_METADATA_PREFIX", TTC_METADATA_PREFIX)
_TTC_OUTPUT_PREFIX = os.getenv("TTC_OUTPUT_PREFIX", TTC_OUTPUT_PREFIX)
AWS_REGION = os.getenv("AWS_REGION")
OPENSEARCH_ENDPOINT_URL = os.getenv("OPENSEARCH_ENDPOINT_URL")
OPENSEARCH_INDEX = os.getenv("OPENSEARCH_INDEX", "ttc-index")
S3_ENDPOINT_URL = os.getenv("S3_ENDPOINT_URL")

# Instantiate wrapper objects for the sentence-transformers models
# to re-use across invocations
RETRIEVER = embedder.Embedder()
RERANKER = reranker.Reranker()

# Constants
NO_DATA_FIELDS_MESSAGE = (
    "No relevant data fields identified from Schematron errors for TTC processing"
)


@event_source(data_class=SQSEvent)
def handler(event: SQSEvent, _: LambdaContext) -> dict:
    """Text to Code lambda entry point.

    :param event: The SQS event containing the S3 event data for processing.
    :param _: The Lambda context object.
    :return: A dictionary containing the status code, message, and any relevant data about the processing results.
    """
    auth = lambda_handler.create_aws_auth()
    opensearch_client = lambda_handler.create_opensearch_client(auth)
    s3_client = lambda_handler.create_s3_client()

    logger.info(f"Received event with {len(event['Records'])} record(s)")

    failures = []
    successes = []

    for record in event.records:
        try:
            process_record(record, s3_client, opensearch_client)
            successes.append(record.message_id)
        except Exception as e:
            logger.exception(f"Error processing record: {e}", message_id=record.message_id)
            failures.append({"message_id": record.message_id, "error": str(e)})
    return (
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


def process_record(record: SQSRecord, s3_client: BaseClient, opensearch_client: OpenSearch) -> None:
    """Process each SQS record.

    :param record: The SQS record to process
    """
    if not record.body:
        logger.warning("Empty SQS body", message_id=record.message_id)
        return

    s3_event = json.loads(record.body)

    # Parse the EventBridge S3 event from the SQS message body
    eventbridge_data = lambda_handler.get_eventbridge_data_from_s3_event(s3_event)
    object_key = eventbridge_data["object_key"]
    bucket_name = eventbridge_data.get("bucket_name") or S3_BUCKET
    logger.info(f"Processing S3 Object: s3://{bucket_name}/{object_key}")

    # Extract persistence_id from the RR object key
    persistence_id = lambda_handler.get_persistence_id(object_key, _TTC_INPUT_PREFIX)
    logger.info(f"Extracted persistence_id: {persistence_id}")

    with logger.append_context_keys(
        persistence_id=persistence_id,
    ):
        _process_record_pipeline(persistence_id, s3_client, opensearch_client)


def _load_schematron_data_fields(persistence_id: str, s3_client: BaseClient) -> list:
    """Load Schematron errors from S3 and extract relevant fields.

    :param persistence_id: The persistence ID extracted from the S3 object key
    :param s3_client: The S3 client to use for fetching files.
    :param bucket_name: The S3 bucket name to read from.
    :return: The relevant Schematron data fields for TTC processing.
    """
    object_key = f"{_SCHEMATRON_ERROR_PREFIX}{persistence_id}"
    logger.info("Loading Schematron errors", s3_key=f"s3://{_S3_BUCKET}/{object_key}")
    schematron_errors = lambda_handler.get_file_content_from_s3(
        bucket_name=_S3_BUCKET,
        object_key=object_key,
        s3_client=s3_client,
    )

    # Process Schematron errors to identify relevant data fields for TTC processing
    logger.info("Extracting relevant fields")
    return schematron_processor.get_data_fields_from_schematron_error(schematron_errors)


def _load_original_eicr(persistence_id: str, s3_client: BaseClient) -> str:
    """Load the original eICR from S3.

    :param persistence_id: The persistence ID extracted from the S3 object key
    :param s3_client: The S3 client to use for fetching files.
    :param bucket_name: The S3 bucket name to read from.
    :return: The original eICR content.
    """
    object_key = f"{_EICR_INPUT_PREFIX}{persistence_id}"
    logger.info(f"Retrieving eICR from s3://{_S3_BUCKET}/{object_key}")
    original_eicr_content = lambda_handler.get_file_content_from_s3(
        bucket_name=_S3_BUCKET, object_key=object_key, s3_client=s3_client
    )
    logger.info(f"Retrieved eICR content for persistence_id {persistence_id}")
    return original_eicr_content


def _process_schematron_errors(
    original_eicr_content: str,
    schematron_errors: list[SchematronErrorDetail],
    opensearch_client: OpenSearch,
) -> list[SchematronErrorDetail]:
    """Process Schematron errors for TTC.

    :param original_eicr_content: The original eICR content.
    :param schematron_data_fields: The relevant Schematron data fields for TTC processing.
    :param opensearch_client: The OpenSearch client.
    :param ttc_output: The TTC output dictionary.
    :param ttc_metadata_output: The TTC metadata output dictionary.
    """
    # Evaluate candidates and select relevant text for each error in the eICR
    for schematron_error_instance in schematron_errors:
        data_field = schematron_error_instance.field
        criteria = evaluator.get_evaluation_criteria_for_data_field(data_field)

        text_candidates = eicr_processor.EicrProcessor(original_eicr_content).get_text_candidates(
            schematron_error_instance.error_context, data_field
        )

        logger.info(
            "Evaluating candidates and selecting relevant text for each error in the eICR for persistence_id"
        )

        selected_candidate = evaluator.select_relevant_text(
            candidates=text_candidates, criteria=criteria
        )

        schematron_error_instance.candidate = selected_candidate

        logger.info(
            "Embedding the relevant text strings for each error in the eICR for persistence_id"
        )

        if selected_candidate is None:
            continue

        vector_embedding = RETRIEVER.embed(selected_candidate.value)

        vector_parameters = query_models.VectorSearchParams(
            vector=vector_embedding.tolist(), data_field=data_field
        )

        logger.info(
            "Querying OpenSearch with the relevant text strings and retrieving code suggestions for persistence_id"
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

        ranked_results = RERANKER.rerank(selected_candidate.value, retrieved_loinc_names)
        best_result = {r.source.description: r.source for r in results_list}[
            ranked_results[0]["code_string"]
        ]
        new_code = Code(
            code=best_result.loinc_code,
            code_system="http://loinc.org",
            code_system_name="LOINC",
            display_name=best_result.description,
            original_text=selected_candidate.value,
        )

        schematron_error_instance.opensearch_retrieved_scores = opensearch_retrieved_scores
        schematron_error_instance.reranker_processed_results = ranked_results
        schematron_error_instance.new_translation = new_code

    return schematron_errors


def _save_ttc_outputs(
    persistence_id: str,
    ttc_output: TTCOutput,
    ttc_metadata_output: TTCMetadata,
    s3_client: BaseClient,
) -> None:
    """Save TTC output and metadata output to S3.

    :param persistence_id: The persistence ID extracted from the S3 object key
    :param ttc_output: The TTC output dictionary.
    :param ttc_metadata_output: The TTC metadata output dictionary.
    :param s3_client: The S3 client to use for uploading files.
    :param bucket_name: The S3 bucket name to write to.
    """
    # Save the TTC output to S3 for the Augmentation Lambda to consume
    logger.info(f"Saving TTC output to S3 for persistence_id {persistence_id}")
    lambda_handler.put_file(
        file_obj=io.BytesIO(ttc_output.model_dump_json().encode("utf-8")),
        bucket_name=_S3_BUCKET,
        object_key=f"{_TTC_OUTPUT_PREFIX}{persistence_id}",
        s3_client=s3_client,
    )

    # Save the TTC metadata output for completing model evaluation and analysis of TTC results
    logger.info(f"Saving TTC metadata output to S3 for persistence_id {persistence_id}")
    lambda_handler.put_file(
        file_obj=io.BytesIO(ttc_metadata_output.model_dump_json().encode("utf-8")),
        bucket_name=_S3_BUCKET,
        object_key=f"{_TTC_METADATA_PREFIX}{persistence_id}",
        s3_client=s3_client,
    )


def _process_record_pipeline(
    persistence_id: str,
    s3_client: BaseClient,
    opensearch_client: OpenSearch,
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
    :param bucket_name: The S3 bucket name extracted from the event, or the default.
    """
    logger.info("Starting TTC processing")
    schematron_data_fields = _load_schematron_data_fields(persistence_id, s3_client)

    message = None

    if not schematron_data_fields:
        logger.warning(
            f"No data fields found from Schematron errors for TTC processing for persistence_id: {persistence_id}"
        )
        message = NO_DATA_FIELDS_MESSAGE
        logger.info(f"Saving TTC metadata output to S3 for persistence_id {persistence_id}")
        lambda_handler.put_file(
            file_obj=io.BytesIO(
                json.dumps(
                    TTCMetadata(
                        persistance_id=persistence_id,
                        message=message,
                        eicr_metadata=None,
                        schematron_errors=[],
                        processed_at=datetime.now(UTC),
                    ),
                    default=str,
                ).encode("utf-8")
            ),
            bucket_name=_S3_BUCKET,
            object_key=f"{_TTC_METADATA_PREFIX}{persistence_id}",
            s3_client=s3_client,
        )
        return {
            "statusCode": 400,
            "message": "No data fields found from Schematron errors for TTC processing",
        }

    original_eicr_content = _load_original_eicr(persistence_id, s3_client)
    schematron_errors = _process_schematron_errors(
        original_eicr_content,
        schematron_data_fields,
        opensearch_client,
    )
    ttc_output = TTCOutput(
        message=None,
        persistance_id=persistence_id,
        nonstandard_codes=[x.to_nonstandard_code_replacement() for x in schematron_errors],
    )

    ttc_metadata = TTCMetadata(
        persistance_id=persistence_id,
        message=None,
        eicr_metadata=EicrProcessor(original_eicr_content).eicr_metadata,
        schematron_errors=schematron_errors,
        processed_at=datetime.now(UTC),
    )

    _save_ttc_outputs(persistence_id, ttc_output, ttc_metadata, s3_client)

    has_matches = len(ttc_output.nonstandard_codes)

    if not has_matches:
        return {
            "statusCode": 200,
            "message": "TTC processed successfully, but no relevant candidates or code matches were found.",
            "result": "no_matches_found",
        }

    return {
        "statusCode": 200,
        "message": "TTC processed successfully with matches.",
        "result": "matched",
    }
