import io
import json
import os

from aws_lambda_powertools import Logger
from aws_lambda_powertools.utilities.data_classes import SQSEvent
from aws_lambda_powertools.utilities.data_classes import event_source
from aws_lambda_powertools.utilities.data_classes.sqs_event import SQSRecord
from aws_lambda_powertools.utilities.typing import LambdaContext
from botocore.client import BaseClient

import lambda_handler
from augmentation.models import TTCAugmenterConfig
from augmentation.models.application import TTCAugmenterOutput
from augmentation.services.eicr_augmenter import EICRAugmenter
from shared_models import NonstandardCodeInstance
from shared_models import TTCAugmenterInput

logger = Logger(service="augmentation-lambda")

# Environment variables
S3_BUCKET = os.getenv("S3_BUCKET", "dibbs-text-to-code")
TTC_INPUT_PREFIX = os.getenv("TTC_INPUT_PREFIX", "TextToCodeSubmissionV2/")
TTC_OUTPUT_PREFIX = os.getenv("TTC_OUTPUT_PREFIX", "TTCAugmentationMetadataV2/")
AUGMENTED_EICR_PREFIX = os.getenv("AUGMENTED_EICR_PREFIX", "AugmentationEICRV2/")
AUGMENTATION_METADATA_PREFIX = os.getenv("AUGMENTATION_METADATA_PREFIX", "AugmentationMetadataV2/")


@event_source(data_class=SQSEvent)
@logger.inject_lambda_context
def handler(event: SQSEvent, context: LambdaContext) -> dict:
    """AWS Lambda handler for augmenting eICRs with nonstandard codes.

    Triggered by S3 events when TTC output objects are created in TTCAugmentationMetadataV2/.
    Reads TTC output and original eICR from S3, performs augmentation, and writes results to S3.

    :param event: The SQS event containing S3 event data.
    :param context: The AWS Lambda context object.
    :return: A dictionary containing processing results and any batch item failures.
    """
    s3_client = lambda_handler.create_s3_client()

    logger.info("Received event", record_count=len(event["Records"]))

    failures = []
    successes = []

    for record in event.records:
        try:
            _process_record(record, s3_client)
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
            "statusCode": 207,
            "message": "Augmentation processed with some failures!",
            "failures": failures,
            "num_failure_eicrs": len(failures),
            "num_success_eicrs": len(successes),
        }
        if failures
        else {
            "statusCode": 200,
            "message": "Augmentation processed successfully!",
            "num_success_eicrs": len(successes),
        }
    )

    logger.info(
        "Augmentation invocation completed",
        status="partial_failure" if failures else "success",
        num_failure_eicrs=len(failures),
        num_success_eicrs=len(successes),
    )

    return result


def _process_record(record: SQSRecord, s3_client: BaseClient) -> None:
    """Process a single SQS record containing an S3 event.

    :param record: The SQS record with an EventBridge S3 event in the body.
    :param s3_client: The S3 client to use for reading and writing files.
    """
    if not record.body:
        logger.warning("Empty SQS body", message_id=record.message_id, status="skipped")
        return

    s3_event = json.loads(record.body)

    eventbridge_data = lambda_handler.get_eventbridge_data_from_s3_event(s3_event)
    object_key = eventbridge_data["object_key"]
    bucket_name = eventbridge_data.get("bucket_name") or S3_BUCKET

    persistence_id = lambda_handler.get_persistence_id(object_key, TTC_OUTPUT_PREFIX)

    with logger.append_context_keys(
        persistence_id=persistence_id,
        bucket_name=bucket_name,
        trigger_s3_key=object_key,
    ):
        logger.info("Processing S3 object", status="processing")

        ttc_output = _load_ttc_output(persistence_id, s3_client, bucket_name)
        original_eicr = _load_original_eicr(persistence_id, s3_client, bucket_name)
        nonstandard_codes = _parse_nonstandard_codes(ttc_output)

        augmenter_input = TTCAugmenterInput(
            eicr_id=persistence_id,
            nonstandard_codes=nonstandard_codes,
        )

        # Currently only supports eICR augmentation. Other document types (e.g. from
        # ecr-refiner or other services) may need different augmentation strategies.
        config = TTCAugmenterConfig()
        augmenter = EICRAugmenter(
            document=original_eicr,
            nonstandard_codes=augmenter_input.nonstandard_codes,
            config=config,
        )

        metadata = augmenter.augment()

        output = TTCAugmenterOutput(
            eicr_id=augmenter_input.eicr_id,
            augmented_eicr=augmenter.augmented_xml,
            metadata=metadata,
        )

        _save_augmentation_outputs(persistence_id, output, s3_client, bucket_name)
        logger.info("Augmentation processing completed", status="success")


def _load_ttc_output(persistence_id: str, s3_client: BaseClient, bucket_name: str) -> dict:
    """Load TTC output from S3.

    :param persistence_id: The persistence ID for the S3 object key.
    :param s3_client: The S3 client.
    :param bucket_name: The S3 bucket name.
    :return: The parsed TTC output dictionary.
    """
    object_key = f"{TTC_OUTPUT_PREFIX}{persistence_id}"
    logger.info(
        "Retrieving TTC output from S3",
        bucket_name=bucket_name,
        s3_key=object_key,
        status="processing",
    )
    content = lambda_handler.get_file_content_from_s3(
        bucket_name=bucket_name, object_key=object_key, s3_client=s3_client
    )
    return json.loads(content)


def _load_original_eicr(persistence_id: str, s3_client: BaseClient, bucket_name: str) -> str:
    """Load original eICR XML from S3.

    :param persistence_id: The persistence ID for the S3 object key.
    :param s3_client: The S3 client.
    :param bucket_name: The S3 bucket name.
    :return: The raw eICR XML string.
    """
    object_key = f"{TTC_INPUT_PREFIX}{persistence_id}"
    logger.info(
        "Retrieving eICR from S3",
        bucket_name=bucket_name,
        s3_key=object_key,
        status="processing",
    )
    return lambda_handler.get_file_content_from_s3(
        bucket_name=bucket_name, object_key=object_key, s3_client=s3_client
    )


def _parse_nonstandard_codes(ttc_output: dict) -> list[NonstandardCodeInstance]:
    """Parse nonstandard codes from TTC output.

    The TTC Lambda writes NonstandardCodeInstance model dumps to the schematron_errors
    field of the TTC output. This function validates and reconstructs them.

    :param ttc_output: The TTC output dictionary from S3.
    :return: A list of NonstandardCodeInstance objects.
    """
    codes = []
    for entries in ttc_output.get("schematron_errors", {}).values():
        for entry in entries:
            if "new_translation" in entry:
                codes.append(NonstandardCodeInstance.model_validate(entry))
    return codes


def _save_augmentation_outputs(
    persistence_id: str,
    output: TTCAugmenterOutput,
    s3_client: BaseClient,
    bucket_name: str,
) -> None:
    """Save augmented eICR and metadata to S3.

    :param persistence_id: The persistence ID for the S3 object key.
    :param output: The augmentation output containing the augmented eICR and metadata.
    :param s3_client: The S3 client to use for uploading files.
    :param bucket_name: The S3 bucket name to write to.
    """
    augmented_eicr_key = f"{AUGMENTED_EICR_PREFIX}{persistence_id}"
    augmentation_metadata_key = f"{AUGMENTATION_METADATA_PREFIX}{persistence_id}"

    lambda_handler.put_file(
        file_obj=io.BytesIO(output.augmented_eicr.encode("utf-8")),
        bucket_name=bucket_name,
        object_key=augmented_eicr_key,
        s3_client=s3_client,
    )
    logger.info(
        "Saved augmented eICR to S3",
        bucket_name=bucket_name,
        s3_key=augmented_eicr_key,
        status="success",
    )

    lambda_handler.put_file(
        file_obj=io.BytesIO(output.metadata.model_dump_json().encode("utf-8")),
        bucket_name=bucket_name,
        object_key=augmentation_metadata_key,
        s3_client=s3_client,
    )

    logger.info(
        "Saved augmentation metadata to S3",
        bucket_name=bucket_name,
        s3_key=augmentation_metadata_key,
        status="success",
    )
