import json
import os

from aws_lambda_powertools import Logger
from aws_lambda_powertools.utilities.data_classes import (SQSEvent, SQSRecord,
                                                          event_source)
from aws_lambda_powertools.utilities.typing import LambdaContext
from text_to_code.services import schematron_processor

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

@event_source(data_class=SQSEvent)
def handler(event: SQSEvent, context: LambdaContext):
    """
    Text to Code lambda entry point
    """
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
    return {"statusCode": 200, "message": "TTC processed with some failures!", "failures": failures, "num_failures": len(failures), "num_successes": len(successes)} if failures else {"statusCode": 200, "message": "TTC processed successfully!", "num_successes": len(successes)}


def process_record(record: SQSRecord) -> None: 
    """
    Process each SQS record.

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
        bucket=bucket,
        object_key=object_key,
        message_id=record.message_id,
    ):
        _process_record_pipeline(bucket, persistence_id)


def _process_record_pipeline(bucket: str, persistence_id: str) -> None:
    """
    The main pipeline for processing each record, which includes:
    - Retrieving Schematron errors from S3
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
    logger.info("Starting TTC processing")
    # S3 GET Schematron errors
    # TODO: Confirm with APHL that the Schematron errors will be stored in the same bucket and follow a consistent naming convention that allows us to derive the Schematron error object key from the persistence_id.

    schematron_object_key = f"{SCHEMATRON_ERROR_PREFIX}{persistence_id}"
    logger.info("Loading Schematron errors", s3_key=schematron_object_key)
    # schematron_errors = s3_handler.get_file_content_from_s3(bucket_name=bucket,
    #                                                         object_key=schematron_object_key,)
    # logger.info(f"Retrieved Schematron errors for persistence_id {persistence_id}: {schematron_errors}")

    # Process Schematron errors to identify relevant data fields for TTC processing
    logger.info("Extracting relevant fields")
    # relevant_data_fields = schematron_processor.get_data_fields_from_schematron_error(schematron_errors)
    # if not relevant_data_fields:
    #     logger.warning(f"No relevant data fields found from Schematron errors for TTC processing for persistence_id: {persistence_id}")
    #     return

    # Construct eICR path: s3://<bucket_name>/<EICR_Input_Prefix>/<persistance_id>
    logger.info(f"Retrieving eICR from s3://{bucket}/{EICR_INPUT_PREFIX}{persistence_id}")

    # S3 GET eICR
    original_eicr_object_key = f"{EICR_INPUT_PREFIX}{persistence_id}"
    logger.info("Loading eICR", s3_key=original_eicr_object_key)
    # original_eicr_content = s3_handler.get_file_content_from_s3(bucket_name=bucket, object_key=original_eicr_object_key)
    logger.info(f"Retrieved eICR content {original_eicr_object_key}")

    # Process the eICR for TTC
    logger.info(f"Starting eICR processing for persistence_id {persistence_id}")
    # TODO: Add relevant eicr_processor code to retrieve the candidate texts for each error in a given eICR, evaluate those candidates, and select the most relevant text string for each error to submit to OpenSearch.

    # Evaluate candidates and select relevant text for each error in the eICR
    logger.info(f"Evaluating candidates and selecting relevant text for each error in the eICR for persistence_id {persistence_id}")
    # For each error, evaluate candidates and select the most relevant text string to submit to OpenSearch
    # TODO: Implement the logic from text_to_code.services.evaluator
    # TODO: If there are no relevant text strings to submit to OpenSearch for any errors, log this and skip the OpenSearch submission step.

    # Embed the relevant text strings for each error in the eICR
    logger.info(f"Embedding the relevant text strings for each error in the eICR for persistence_id {persistence_id}")
    # TODO: Implement the logic to embed the relevant text strings for each error     
    
    # Query OpenSearch with the relevant text strings and retrieve the code suggestions
    logger.info(f"Querying OpenSearch with the relevant text strings and retrieving code suggestions for persistence_id {persistence_id}")
    # TODO: Implement the query logic here

    # Create output to pass to Augmentation Lambda
    logger.info(f"Creating output to pass to Augmentation Lambda for persistence_id {persistence_id}")
    # TODO: Add function to generate augmentation output
    # augmentation_output_key = f"{TTC_OUTPUT_PREFIX}{persistence_id}"
    # s3_handler.put_file(file_obj = augmentation_data, bucket_name: eventbridge_data['bucket_name'], object_key = augmentation_output_key)
    logger.info(f"Saved TTC output to s3://{bucket}/{TTC_OUTPUT_PREFIX}{persistence_id}")

    # Create the metadata object to save in S3 for analysis of TTC results
    logger.info(f"Creating the metadata object to save in S3 for analysis of TTC results for persistence_id {persistence_id}")
    # TODO: Add function to generate metadata content (similar to augmentation output)
    # metadata_output_key = f"{TTC_METADATA_PREFIX}{persistence_id}"
    # s3_handler.put_file(file_obj = metadata_content, bucket_name: eventbridge_data['bucket_name'], object_key = metadata_output_key)
    logger.info(f"Saved TTC metadata to s3://{bucket}/{TTC_METADATA_PREFIX}{persistence_id}")   

    return {"statusCode": 200, "message": "TTC processed successfully!"}
