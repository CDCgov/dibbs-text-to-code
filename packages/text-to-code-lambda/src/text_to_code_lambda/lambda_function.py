import io
import json
import os

import lambda_handler
from aws_lambda_powertools import Logger
from aws_lambda_powertools.utilities.data_classes import SQSEvent
from aws_lambda_powertools.utilities.data_classes import SQSRecord
from aws_lambda_powertools.utilities.data_classes import event_source
from aws_lambda_powertools.utilities.typing import LambdaContext
from botocore.client import BaseClient
from opensearchpy import OpenSearch
from text_to_code.models import eicr as eicr_models
from text_to_code.models import query as query_models
from text_to_code.services import eicr_processor
from text_to_code.services import embedder
from text_to_code.services import evaluator
from text_to_code.services import schematron_processor
from text_to_code.services.query import QueryBuilder

# Initialize the logger
logger = Logger(service="ttc")

# Environment variables
EICR_INPUT_PREFIX = os.getenv("EICR_INPUT_PREFIX", "eCRMessageV2/")
SCHEMATRON_ERROR_PREFIX = os.getenv("SCHEMATRON_ERROR_PREFIX", "schematronErrors/")
TTC_INPUT_PREFIX = os.getenv("TTC_INPUT_PREFIX", "TextToCodeSubmission/")
TTC_OUTPUT_PREFIX = os.getenv("TTC_OUTPUT_PREFIX", "TTCOutput/")
TTC_METADATA_PREFIX = os.getenv("TTC_METADATA_PREFIX", "TTCMetadata/")
AWS_REGION = os.getenv("AWS_REGION")
S3_ENDPOINT_URL = os.getenv("S3_ENDPOINT_URL")
OPENSEARCH_ENDPOINT_URL = os.getenv("OPENSEARCH_ENDPOINT_URL")
OPENSEARCH_INDEX = os.getenv("OPENSEARCH_INDEX", "ttc-index")

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
    bucket = eventbridge_data["bucket_name"]
    object_key = eventbridge_data["object_key"]
    logger.info(f"Processing S3 Object: s3://{bucket}/{object_key}")

    # Extract persistence_id from the RR object key
    persistence_id = lambda_handler.get_persistence_id(object_key, TTC_INPUT_PREFIX)
    logger.info(f"Extracted persistence_id: {persistence_id}")

    with logger.append_context_keys(
        persistence_id=persistence_id,
    ):
        _process_record_pipeline(bucket, persistence_id, s3_client, opensearch_client)


def _process_record_pipeline(
    bucket: str,
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

    :param bucket: The name of the S3 bucket
    :param persistence_id: The persistence ID extracted from the S3 object key
    """
    # TODO: Update the ttc_output to ensure it matches and uses the expected model once ticket #263 is completed
    ttc_output: dict = {"persistence_id": "", "eicr_metadata": {}, "schematron_errors": {}}
    ttc_metadata_output: dict = {
        "persistence_id": "",
        "eicr_metadata": {},
        "schematron_errors": {},
    }
    ttc_output["persistence_id"] = persistence_id
    ttc_metadata_output["persistence_id"] = persistence_id

    logger.info("Starting TTC processing")
    # S3 GET Schematron errors
    # TODO: Confirm with APHL that the Schematron errors will be stored in the same bucket and follow a consistent naming convention that allows us to derive the Schematron error object key from the persistence_id.
    schematron_bucket_name = SCHEMATRON_ERROR_PREFIX.split("/")[0]
    logger.info("Loading Schematron errors", s3_key=f"{schematron_bucket_name}{persistence_id}")
    schematron_errors = lambda_handler.get_file_content_from_s3(
        bucket_name=schematron_bucket_name,
        object_key=f"{persistence_id}",
    )

    # Process Schematron errors to identify relevant data fields for TTC processing
    logger.info("Extracting relevant fields")
    schematron_data_fields = schematron_processor.get_data_fields_from_schematron_error(
        schematron_errors
    )

    if not schematron_data_fields:
        logger.warning(
            f"No data fields found from Schematron errors for TTC processing for persistence_id: {persistence_id}"
        )
        # TODO: update this output to save metadata about the lack of TTC processing due to no relevant data fields being identified to S3 for analysis
        ttc_output["message"] = (
            "No relevant data fields identified from Schematron errors for TTC processing"
        )
        # TODO: Is this enough information to return early?
        return ttc_output

    # Construct eICR path: s3://<bucket_name>/<EICR_Input_Prefix>/<persistance_id>
    logger.info(f"Retrieving eICR from s3://{EICR_INPUT_PREFIX}{persistence_id}")

    # S3 GET eICR
    ecr_bucket_name = EICR_INPUT_PREFIX.split("/")[0]
    logger.info("Loading eICR", s3_key=f"{ecr_bucket_name}/{persistence_id}")
    original_eicr_content = lambda_handler.get_file_content_from_s3(
        bucket_name=bucket, object_key=persistence_id
    )
    logger.info(f"Retrieved eICR content for persistence_id {persistence_id}")

    # # Process the eICR for TTC
    # Retrieve eICR Metadata
    eicr_metadata = eicr_processor.EicrProcessor(original_eicr_content).eicr_metadata

    ttc_output["eicr_metadata"] = eicr_metadata
    ttc_metadata_output["eicr_metadata"] = eicr_metadata

    # TODO: Note: this looping logic will need to be updated once the outputs for
    # the schematron_processor (ticket 327) is updated.
    for data_field, error_xpaths in schematron_data_fields.items():
        # Get evaluation criteria for the current data field
        criteria = evaluator.get_evaluation_criteria_for_data_field(data_field)
        ttc_output["schematron_errors"][data_field] = []
        ttc_metadata_output["schematron_errors"][data_field] = []
        # Retrieve candidate text strings for each error in the eICR based on the Schematron error_context and the original eICR content
        for error_context in error_xpaths:
            # TODO: update the error context addition to ttc_output once ticket #327 is completed
            error = {}
            error["error_context"] = error_context
            text_candidates = eicr_processor.EicrProcessor(
                original_eicr_content
            ).get_text_candidates(error_context, data_field)
            # TODO: update the text_candidates addition to ttc_output once ticket #327 is completed
            error["text_candidates"] = text_candidates

            # Evaluate candidates and select relevant text for each error in the eICR
            logger.info(
                f"Evaluating candidates and selecting relevant text for each error in the eICR for persistence_id {persistence_id}"
            )

            # For each error, evaluate candidates and select the most relevant candidate value to submit to OpenSearch
            selected_candidate = evaluator.select_relevant_text(
                candidates=text_candidates, criteria=criteria
            )

            # TODO: remove this hardcoding with actual selected_candidate from the evaluator once we have a better test example eICR
            selected_candidate = eicr_models.Candidate(
                value="test test test",
                xpath=eicr_models.LabXPaths.CODE_DISPLAY_NAME,
                system="LOINC",
            )
            # TODO: update the error context addition to ttc_output once ticket #327 is completed
            error["selected_candidate"] = selected_candidate
            ttc_output["schematron_errors"][data_field].append(error)

            # Embed the relevant text strings for each error in the eICR
            logger.info(
                f"Embedding the relevant text strings for each error in the eICR for persistence_id {persistence_id}"
            )
            # If no relevant text was selected for the error, we can skip the embedding and querying steps for that error
            # TODO: update this to perhaps return better info?
            if selected_candidate is None:
                continue
            # TODO: update embedder with TTC model
            vector_embedding = embedder.Embedder().embed(selected_candidate.value)

            # Generate the OpenSearch query based on the relevant text string embedding and any other relevant information
            vector_parameters = query_models.VectorSearchParams(
                vector=vector_embedding.tolist(), data_field=data_field
            )

            logger.info(
                f"Querying OpenSearch with the relevant text strings and retrieving code suggestions for persistence_id {persistence_id}"
            )
            query = QueryBuilder().with_vector_search(vector_parameters).build()

            # Query OpenSearch with the relevant text strings and retrieve the code suggestions
            opensearch_retrieved_scores = lambda_handler.retrieve_opensearch_results(
                query=query, index=OPENSEARCH_INDEX, opensearch_client=opensearch_client
            )
            error["opensearch_retrieved_scores"] = opensearch_retrieved_scores
            ttc_metadata_output["schematron_errors"][data_field].append(error)

            # TODO: Add Reranker code here once added to the Evaluator service

    # Save the TTC output to S3 for the Augmentation Lambda to consume
    logger.info(f"Saving TTC output to S3 for persistence_id {persistence_id}")
    ttc_output_bucket_name = TTC_OUTPUT_PREFIX.split("/")[0]
    lambda_handler.put_file(
        file_obj=io.BytesIO(json.dumps(ttc_output, default=str).encode("utf-8")),
        bucket_name=ttc_output_bucket_name,
        object_key=persistence_id,
    )

    # Save the TTC metadata output for completing model evaluation and analysis of TTC results
    logger.info(f"Saving TTC metadata output to S3 for persistence_id {persistence_id}")
    ttc_metadata_output_bucket_name = TTC_METADATA_PREFIX.split("/")[0]
    lambda_handler.put_file(
        file_obj=io.BytesIO(json.dumps(ttc_metadata_output, default=str).encode("utf-8")),
        bucket_name=ttc_metadata_output_bucket_name,
        object_key=persistence_id,
    )

    return {"statusCode": 200, "message": "TTC processed successfully!"}
