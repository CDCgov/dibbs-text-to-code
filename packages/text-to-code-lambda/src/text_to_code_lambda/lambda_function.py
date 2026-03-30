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
from text_to_code.models import query as query_models
from text_to_code.services import eicr_processor
from text_to_code.services import embedder
from text_to_code.services import evaluator
from text_to_code.services import reranker
from text_to_code.services import schematron_processor
from text_to_code.services.query import QueryBuilder

# Initialize the logger
logger = Logger(service="ttc")

# Environment variables
S3_BUCKET = os.getenv("S3_BUCKET", "dibbs-text-to-code")
EICR_INPUT_PREFIX = os.getenv("EICR_INPUT_PREFIX", "eCRMessageV2/")
SCHEMATRON_ERROR_PREFIX = os.getenv("SCHEMATRON_ERROR_PREFIX", "schematronErrors/")
TTC_INPUT_PREFIX = os.getenv("TTC_INPUT_PREFIX", "TextToCodeValidateSubmissionV2/")
TTC_OUTPUT_PREFIX = os.getenv("TTC_OUTPUT_PREFIX", "TTCOutput/")
TTC_METADATA_PREFIX = os.getenv("TTC_METADATA_PREFIX", "TTCMetadata/")
AWS_REGION = os.getenv("AWS_REGION")
S3_ENDPOINT_URL = os.getenv("S3_ENDPOINT_URL")
OPENSEARCH_ENDPOINT_URL = os.getenv("OPENSEARCH_ENDPOINT_URL")
OPENSEARCH_INDEX = os.getenv("OPENSEARCH_INDEX", "ttc-index")

# Instantiate wrapper objects for the sentence-transformers models
# to re-use across invocations
RETRIEVER = embedder.Embedder()
RERANKER = reranker.Reranker()

# Constants
NO_DATA_FIELDS_MESSAGE = (
    "No relevant data fields identified from Schematron errors for TTC processing"
)

# Cache clients and auth to reuse across Lambda invocations
_cached_auth = None
_cached_opensearch_client = None
_cached_s3_client = None


@event_source(data_class=SQSEvent)
def handler(event: SQSEvent, context: LambdaContext) -> dict:
    """Text to Code lambda entry point.

    :param event: The SQS event containing the S3 event data for processing.
    :param context: The Lambda context object.
    :return: A dictionary containing the status code, message, and any relevant data about the processing results.
    """
    global _cached_auth, _cached_opensearch_client, _cached_s3_client  # noqa: PLW0603

    # Initialize cached clients if they don't exist
    if _cached_auth is None:
        _cached_auth = lambda_handler.create_aws_auth()
    auth = _cached_auth

    if _cached_opensearch_client is None:
        _cached_opensearch_client = lambda_handler.create_opensearch_client(auth)
    opensearch_client = _cached_opensearch_client

    if _cached_s3_client is None:
        _cached_s3_client = lambda_handler.create_s3_client()
    s3_client = _cached_s3_client

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
    # TODO: Update the return values to also include failures per schematron error, not just eicr docs
    # TODO: Update this output to whatever
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
    logger.info(f"Processing S3 Object: s3://{S3_BUCKET}/{object_key}")

    # Extract persistence_id from the RR object key
    persistence_id = lambda_handler.get_persistence_id(object_key, TTC_INPUT_PREFIX)
    logger.info(f"Extracted persistence_id: {persistence_id}")

    with logger.append_context_keys(
        persistence_id=persistence_id,
    ):
        _process_record_pipeline(persistence_id, s3_client, opensearch_client)


def _initialize_ttc_outputs(persistence_id: str) -> tuple[dict, dict]:
    """Initialize TTC output and metadata output dictionaries.

    :param persistence_id: The persistence ID extracted from the S3 object key
    :return: The TTC output and TTC metadata output dictionaries.
    """
    # TODO: Update the ttc_output to ensure it matches and uses the expected model once ticket #263 is completed
    ttc_output: dict = {"persistence_id": "", "eicr_metadata": {}, "schematron_errors": {}}
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


def _load_schematron_data_fields(persistence_id: str, s3_client: BaseClient) -> list:
    """Load Schematron errors from S3 and extract relevant fields.

    :param persistence_id: The persistence ID extracted from the S3 object key
    :param s3_client: The S3 client to use for fetching files.
    :return: The relevant Schematron data fields for TTC processing.
    """
    object_key = f"{SCHEMATRON_ERROR_PREFIX}{persistence_id}"
    logger.info("Loading Schematron errors", s3_key=f"s3://{S3_BUCKET}/{object_key}")
    schematron_errors = lambda_handler.get_file_content_from_s3(
        bucket_name=S3_BUCKET,
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
    :return: The original eICR content.
    """
    object_key = f"{EICR_INPUT_PREFIX}{persistence_id}"
    logger.info(f"Retrieving eICR from s3://{S3_BUCKET}/{object_key}")
    original_eicr_content = lambda_handler.get_file_content_from_s3(
        bucket_name=S3_BUCKET, object_key=object_key, s3_client=s3_client
    )
    logger.info(f"Retrieved eICR content for persistence_id {persistence_id}")
    return original_eicr_content


def _populate_eicr_metadata(
    original_eicr_content: str,
    ttc_output: dict,
    ttc_metadata_output: dict,
) -> None:
    """Populate eICR metadata on TTC outputs.

    :param original_eicr_content: The original eICR content.
    :param ttc_output: The TTC output dictionary.
    :param ttc_metadata_output: The TTC metadata output dictionary.
    """
    # # Process the eICR for TTC
    # Retrieve eICR Metadata
    eicr_metadata = eicr_processor.EicrProcessor(original_eicr_content).eicr_metadata

    ttc_output["eicr_metadata"] = eicr_metadata
    ttc_metadata_output["eicr_metadata"] = eicr_metadata


def _process_schematron_errors(
    original_eicr_content: str,
    schematron_data_fields: list,
    opensearch_client: OpenSearch,
    ttc_output: dict,
    ttc_metadata_output: dict,
) -> None:
    """Process Schematron errors for TTC.

    :param original_eicr_content: The original eICR content.
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
        if data_field not in ttc_metadata_output["schematron_errors"]:
            ttc_metadata_output["schematron_errors"][data_field] = []

        text_candidates = eicr_processor.EicrProcessor(original_eicr_content).get_text_candidates(
            error.error_context, data_field
        )

        logger.info(
            "Evaluating candidates and selecting relevant text for each error in the eICR for persistence_id"
        )

        selected_candidate = evaluator.select_relevant_text(
            candidates=text_candidates, criteria=criteria
        )

        error.candidate = selected_candidate
        ttc_output["schematron_errors"][data_field].append(error.model_dump())

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

        metadata_error = error.model_dump()
        metadata_error["opensearch_retrieved_scores"] = opensearch_retrieved_scores
        metadata_error["reranker_processed_results"] = ranked_results
        ttc_metadata_output["schematron_errors"][data_field].append(metadata_error)


def _save_ttc_outputs(
    persistence_id: str, ttc_output: dict, ttc_metadata_output: dict, s3_client: BaseClient
) -> None:
    """Save TTC output and metadata output to S3.

    :param persistence_id: The persistence ID extracted from the S3 object key
    :param ttc_output: The TTC output dictionary.
    :param ttc_metadata_output: The TTC metadata output dictionary.
    :param s3_client: The S3 client to use for uploading files.
    """
    # Save the TTC output to S3 for the Augmentation Lambda to consume
    logger.info(f"Saving TTC output to S3 for persistence_id {persistence_id}")
    lambda_handler.put_file(
        file_obj=io.BytesIO(json.dumps(ttc_output, default=str).encode("utf-8")),
        bucket_name=S3_BUCKET,
        object_key=f"{TTC_OUTPUT_PREFIX}{persistence_id}",
        s3_client=s3_client,
    )

    # Save the TTC metadata output for completing model evaluation and analysis of TTC results
    logger.info(f"Saving TTC metadata output to S3 for persistence_id {persistence_id}")
    lambda_handler.put_file(
        file_obj=io.BytesIO(json.dumps(ttc_metadata_output, default=str).encode("utf-8")),
        bucket_name=S3_BUCKET,
        object_key=f"{TTC_METADATA_PREFIX}{persistence_id}",
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
    """
    ttc_output, ttc_metadata_output = _initialize_ttc_outputs(persistence_id)

    logger.info("Starting TTC processing")
    schematron_data_fields = _load_schematron_data_fields(persistence_id, s3_client)

    if not schematron_data_fields:
        logger.warning(
            f"No data fields found from Schematron errors for TTC processing for persistence_id: {persistence_id}"
        )
        ttc_output["message"] = NO_DATA_FIELDS_MESSAGE
        ttc_metadata_output["reason_for_skipping"] = NO_DATA_FIELDS_MESSAGE
        logger.info(f"Saving TTC metadata output to S3 for persistence_id {persistence_id}")
        ttc_metadata_output_bucket_name = TTC_METADATA_PREFIX.split("/")[0]
        lambda_handler.put_file(
            file_obj=io.BytesIO(json.dumps(ttc_metadata_output, default=str).encode("utf-8")),
            bucket_name=ttc_metadata_output_bucket_name,
            object_key=persistence_id,
        )
        return ttc_output

    original_eicr_content = _load_original_eicr(persistence_id, s3_client)
    _populate_eicr_metadata(original_eicr_content, ttc_output, ttc_metadata_output)
    _process_schematron_errors(
        original_eicr_content,
        schematron_data_fields,
        opensearch_client,
        ttc_output,
        ttc_metadata_output,
    )
    _save_ttc_outputs(persistence_id, ttc_output, ttc_metadata_output, s3_client)

    return {"statusCode": 200, "message": "TTC processed successfully!"}
