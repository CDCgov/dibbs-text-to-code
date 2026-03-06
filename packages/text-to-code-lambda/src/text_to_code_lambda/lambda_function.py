import json
import os

from aws_lambda_powertools import Logger
from aws_lambda_powertools.utilities.data_classes import SQSEvent
from aws_lambda_powertools.utilities.data_classes import SQSRecord
from aws_lambda_powertools.utilities.data_classes import event_source
from aws_lambda_powertools.utilities.typing import LambdaContext
from text_to_code.models import query as query_models
from text_to_code.services import eicr_processor
from text_to_code.services import embedder
from text_to_code.services import evaluator
from text_to_code.services import schematron_processor
from text_to_code.services.query import QueryBuilder

from . import s3_handler

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

# Initialize Auth and clients outside of the handler for connection reuse
auth = s3_handler.create_aws_auth()
opensearch_client = s3_handler.create_opensearch_client(auth)
s3_client = s3_handler.create_s3_client()


@event_source(data_class=SQSEvent)
def handler(event: SQSEvent, context: LambdaContext) -> dict:
    """Text to Code lambda entry point."""
    logger.info(f"Received event with {len(event['Records'])} record(s)")

    failures = []
    successes = []

    for record in event.records:
        try:
            process_record(record)
            successes.append(record.message_id)
        except Exception as e:
            logger.exception(f"Error processing record: {e}", message_id=record.message_id)
            failures.append({"message_id": record.message_id, "error": str(e)})
    # TODO: Update the return value
    return (
        {
            "statusCode": 200,
            "message": "TTC processed with some failures!",
            "failures": failures,
            "num_failures": len(failures),
            "num_successes": len(successes),
        }
        if failures
        else {
            "statusCode": 200,
            "message": "TTC processed successfully!",
            "num_successes": len(successes),
        }
    )


def process_record(record: SQSRecord) -> None:
    """Process each SQS record.

    :param record: The SQS record to process
    """
    if not record.body:
        logger.warning("Empty SQS body", message_id=record.message_id)
        return

    s3_event = json.loads(record.body)

    # Parse the EventBridge S3 event from the SQS message body
    eventbridge_data = s3_handler.get_eventbridge_data_from_s3_event(s3_event)
    bucket = eventbridge_data["bucket_name"]
    object_key = eventbridge_data["object_key"]
    logger.info(f"Processing S3 Object: s3://{bucket}/{object_key}")

    # Extract persistence_id from the RR object key
    persistence_id = s3_handler.get_persistence_id(object_key, TTC_INPUT_PREFIX)
    logger.info(f"Extracted persistence_id: {persistence_id}")

    with logger.append_context_keys(
        persistence_id=persistence_id,
    ):
        _process_record_pipeline(bucket, persistence_id)


def _process_record_pipeline(bucket: str, persistence_id: str) -> dict:
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
    # TODO: is persistence_id the same as the original eicr_id?
    ttc_output = {"eicr_id": persistence_id}

    logger.info("Starting TTC processing")
    # S3 GET Schematron errors
    # TODO: Confirm with APHL that the Schematron errors will be stored in the same bucket and follow a consistent naming convention that allows us to derive the Schematron error object key from the persistence_id.
    schematron_bucket_name = SCHEMATRON_ERROR_PREFIX.split("/")[0]
    logger.info("Loading Schematron errors", s3_key=f"{schematron_bucket_name}/{persistence_id}")
    schematron_errors = s3_handler.get_file_content_from_s3(
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
        return None

    # Construct eICR path: s3://<bucket_name>/<EICR_Input_Prefix>/<persistance_id>
    logger.info(f"Retrieving eICR from s3://{EICR_INPUT_PREFIX}{persistence_id}")

    # S3 GET eICR
    ecr_bucket_name = EICR_INPUT_PREFIX.split("/")[0]
    logger.info("Loading eICR", s3_key=f"{ecr_bucket_name}/{persistence_id}")
    original_eicr_content = s3_handler.get_file_content_from_s3(
        bucket_name=bucket, object_key=persistence_id
    )
    logger.info(f"Retrieved eICR content {persistence_id}")

    # Process the eICR for TTC
    logger.info(f"Starting eICR processing for persistence_id {persistence_id}")

    # Note: this looping logic will need to be updated once the outputs for
    # the schematron_processor, eicr_processor, and evaluator are updated.
    for data_field, error_xpaths in schematron_data_fields.items():
        # Get evaluation criteria for the current data field
        criteria = evaluator.get_evaluation_criteria_for_data_field(data_field)
        ttc_output[data_field] = []

        # Retrieve candidate text strings for each error in the eICR based on the Schematron error_context and the original eICR content
        for error_context in error_xpaths:
            text_candidates = eicr_processor.EicrProcessor(
                original_eicr_content
            ).get_text_candidates(error_context, data_field)
            ttc_output[data_field].append(
                {"error_context": error_context, "text_candidates": text_candidates}
            )

            # Evaluate candidates and select relevant text for each error in the eICR
            logger.info(
                f"Evaluating candidates and selecting relevant text for each error in the eICR for persistence_id {persistence_id}"
            )

            # For each error, evaluate candidates and select the most relevant text string to submit to OpenSearch
            selected_text = evaluator.select_relevant_text(
                candidates=text_candidates, criteria=criteria
            )
            ttc_output[data_field][-1]["selected_text"] = selected_text

            # Embed the relevant text strings for each error in the eICR
            logger.info(
                f"Embedding the relevant text strings for each error in the eICR for persistence_id {persistence_id}"
            )
            # If no relevant text string was selected for the error, we can skip the embedding and querying steps for that error
            selected_text = "test test test"
            if selected_text is None:
                continue

            vector_embedding = embedder.Embedder().embed(selected_text)

            # Generate the OpenSearch query based on the relevant text string embedding and any other relevant information
            vector_parameters = query_models.VectorSearchParams(
                vector=vector_embedding, data_field=data_field
            )

            logger.info(
                f"Querying OpenSearch with the relevant text strings and retrieving code suggestions for persistence_id {persistence_id}"
            )
            query = QueryBuilder().with_vector_search(vector_parameters).build()
            print(query)

            # # Query OpenSearch with the relevant text strings and retrieve the code suggestions
            # opensearch_retrieved_scores = opensearch_client.search(
            #     index=OPENSEARCH_INDEX.value,
            #     body=query,
            # )

            # TODO: Add Reranker code here once added to the Evaluator service

            # TODO: Save reranker scores

            # # Create the analytics metadata object to save in S3 for analysis of TTC results
            # logger.info(
            #     f"Creating the analytics metadata object to save in S3 for analysis of TTC results for persistence_id {persistence_id}"
            # )
            # ttc_metadata_output_bucket_name = TTC_METADATA_PREFIX.split("/")[0]
            # s3_handler.put_file(file_obj = metadata_content, bucket_name: ttc_metadata_output_bucket_name, object_key = persistence_id)

            # # Create output to pass to Augmentation Lambda
            # logger.info(
            #     f"Creating output to pass to Augmentation Lambda for persistence_id {persistence_id}"
            # )
            # # TODO: Add function to generate augmentation output
            # # augmentation_output_bucket_name = TTC_OUTPUT_PREFIX.split("/")[0]
            # # s3_handler.put_file(file_obj = augmentation_data, bucket_name = augmentation_output_bucket_name, object_key = persistence_id)
            # logger.info(f"Saved TTC output to s3://{TTC_OUTPUT_PREFIX}{persistence_id}")

    return {"statusCode": 200, "message": "TTC processed successfully!"}
