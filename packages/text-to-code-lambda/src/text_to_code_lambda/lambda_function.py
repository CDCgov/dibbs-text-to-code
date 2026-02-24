import json
import os

from aws_lambda_typing import context as lambda_context
from aws_lambda_typing import events as lambda_events
from aws_lambda_powertools import Logger

from . import s3_handler
from text_to_code.services import schematron_processor

# Initialize the logger
logger = Logger(service="ttc")

# Environment variables
EICR_INPUT_PREFIX = os.getenv("EICR_INPUT_PREFIX", "eCRMessageV2/")
SCHEMATRON_ERROR_PREFIX = os.getenv("SCHEMATRON_ERROR_PREFIX", "schematronErrors/")
TTC_INPUT_PREFIX = os.getenv("TTC_INPUT_PREFIX", "TTCInput/")
TTC_OUTPUT_PREFIX = os.getenv("TTC_OUTPUT_PREFIX", "TTCOutput/")
TTC_METADATA_PREFIX = os.getenv("TTC_METADATA_PREFIX", "TTCMetadata/")
AWS_REGION = os.getenv("AWS_REGION")
S3_ENDPOINT_URL = os.getenv("S3_ENDPOINT_URL")
OPENSEARCH_ENDPOINT_URL = os.getenv("OPENSEARCH_ENDPOINT_URL")

def handler(event: lambda_events.SQSEvent, context: lambda_context.Context):
    """
    Text to Code lambda entry point
    """ 
    logger.info(f"Received event with {len(event.get('Records', []))} record(s)")

    for record in event.get("Records", []):
        body = record.get("body")
        if not body:
            continue
        s3_event = json.loads(body)

        # Parse the EventBridge S3 event from the SQS message body
        eventbridge_data = s3_handler.get_eventbridge_data_from_s3_event(s3_event)
        logger.info(f"Processing S3 Object: s3://{eventbridge_data['bucket_name']}/{eventbridge_data['object_key']}")

        # Extract persistence_id from the RR object key
        persistence_id = s3_handler.get_persistence_id(eventbridge_data["object_key"], TTC_INPUT_PREFIX)
        logger.info(f"Extracted persistence_id: {persistence_id}")

        # S3 GET Schematron errors
        # TODO: Confirm with APHL that the Schematron errors will be stored in the same bucket and follow a consistent naming convention that allows us to derive the Schematron error object key from the persistence_id.
        schematron_errors = s3_handler.get_file_content_from_s3(bucket_name=eventbridge_data["bucket_name"], object_key=f"{SCHEMATRON_ERROR_PREFIX}{persistence_id}")
        logger.info(f"Retrieved Schematron errors for persistence_id {persistence_id}: {schematron_errors}")

        # Process Schematron errors to identify relevant data fields for TTC processing
        logger.info("Processing Schematron errors to identify relevant data fields for TTC processing")
        relevant_data_fields = schematron_processor.get_data_fields_from_schematron_error(schematron_errors)
        if not relevant_data_fields:
            logger.warning(f"No relevant data fields found from Schematron errors for TTC processing for persistence_id: {persistence_id}")
            continue

        # Construct eICR path: s3://<bucket_name>/<EICR_Input_Prefix>/<persistance_id>
        logger.info(f"Retrieving eICR from s3://{eventbridge_data['bucket_name']}/{EICR_INPUT_PREFIX}{persistence_id}")

        # S3 GET eICR
        original_eicr_content = s3_handler.get_file_content_from_s3(bucket_name=eventbridge_data["bucket_name"], object_key=f"{EICR_INPUT_PREFIX}{persistence_id}")
        logger.info(f"Retrieved eICR content for persistence_id {persistence_id}")

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
        # augmentation_output_key = f"{TTC_OUTPUT_PREFIX}{persistence_id}"
        # s3_handler.put_file(file_obj = augmentation_data, bucket_name: eventbridge_data['bucket_name'], object_key = augmentation_output_key)
        logger.info(f"Saved TTC output to s3://{eventbridge_data['bucket_name']}/{TTC_OUTPUT_PREFIX}{persistence_id}")

        # Create the metadata object to save in S3 for analysis of TTC results
        logger.info(f"Creating the metadata object to save in S3 for analysis of TTC results for persistence_id {persistence_id}")
        # metadata_output_key = f"{TTC_METADATA_PREFIX}{persistence_id}"
        # s3_handler.put_file(file_obj = metadata_content, bucket_name: eventbridge_data['bucket_name'], object_key = metadata_output_key)
        logger.info(f"Saved TTC metadata to s3://{eventbridge_data['bucket_name']}/{TTC_METADATA_PREFIX}{persistence_id}")   


    return {"statusCode": 200, "message": "TTC processed successfully!"}
