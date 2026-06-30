import io
import json
import os

from aws_lambda_powertools import Logger
from aws_lambda_powertools.utilities.data_classes import SQSEvent, event_source
from aws_lambda_powertools.utilities.data_classes.sqs_event import SQSRecord
from aws_lambda_powertools.utilities.typing import LambdaContext

import lambda_handler
from augmentation.models import Metadata
from augmentation.models.application import NonstandardCodeInstanceMetadata, TTCAugmenterOutput
from augmentation.services.eicr_augmenter import EICRAugmenter
from shared_models import CdaInstanceIdentifier, PassthroughReason, TTCAugmenterInput
from validation import validate_eicr

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
    logger.info("Received event", record_count=len(event["Records"]))

    failures = []
    successes = []

    for record in event.records:
        try:
            _process_record(record)
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


def _process_record(record: SQSRecord) -> None:
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

        augmenter_input = _load_ttc_output(persistence_id, bucket_name)
        original_eicr = _load_original_eicr(persistence_id, bucket_name)

        output = _build_augmentation_output(
            persistence_id=persistence_id,
            original_eicr=original_eicr,
            augmenter_input=augmenter_input,
        )

        _save_augmentation_outputs(persistence_id, output, bucket_name)
        logger.info(
            "Augmentation processing completed",
            status="passthrough" if output.metadata.passthrough_reason is not None else "success",
            passthrough_reason=output.metadata.passthrough_reason,
        )


def _introduced_validation_error(original_eicr: str, augmented_eicr: str) -> str | None:
    """Return a JSON error string only if augmentation introduced new validation errors.

    Augmentation adds ``<translation>`` children under ``<code>`` and never alters result
    values or observation positions, so a finding that pre-existed in the original eICR has
    an identical ``(error_id, location)`` in both validations and cancels out of the diff.
    Pre-existing findings the augmenter does not own therefore do not block its output.

    A clean augmented result cannot contain anything new, so the original is only
    re-validated when the augmented eICR has findings to diff against. On a validation
    exception the exception text is returned so the caller conservatively passes through.

    :param original_eicr: The original (pre-augmentation) eICR XML string.
    :param augmented_eicr: The augmented eICR XML string.
    :return: A JSON-encoded list of the newly-introduced validation errors, the exception
        text if validation raised, or ``None`` when augmentation introduced nothing.
    """
    try:
        augmented_results = validate_eicr(augmented_eicr)
        if not augmented_results:
            return None
        baseline_results = validate_eicr(original_eicr)
        new_results = sorted(
            set(augmented_results) - set(baseline_results),
            key=lambda result: (result.error_id, result.location),
        )
    except Exception as e:
        logger.exception(
            "Augmentation validation failed; writing original eICR output",
            status="passthrough",
            passthrough_reason=PassthroughReason.AUGMENTATION_VALIDATION_FAILURE,
        )
        return str(e)

    if new_results:
        logger.warning(
            "Augmentation introduced new validation errors; writing original eICR output",
            status="passthrough",
            passthrough_reason=PassthroughReason.AUGMENTATION_VALIDATION_FAILURE,
            new_error_count=len(new_results),
        )
        return json.dumps([result.model_dump() for result in new_results])

    logger.info(
        "Augmented eICR has pre-existing validation findings not introduced by "
        "augmentation; emitting augmented eICR",
        status="success",
        preexisting_error_count=len(augmented_results),
    )
    return None


def _build_augmentation_output(
    persistence_id: str,
    original_eicr: str,
    augmenter_input: TTCAugmenterInput,
) -> TTCAugmenterOutput:
    """Build the augmentation-stage output for a loaded TTC result.

    This function owns the business decision tree:
    - TTC passthrough emits the original eICR.
    - successful augmentation emits the augmented eICR.
    - augmentation failure emits the original eICR.
    - validation failure emits the original eICR.

    :param persistence_id: The stable pipeline/storage ID used for S3 keys.
    :param original_eicr: The original eICR XML string.
    :param augmenter_input: The parsed TTC augmenter input.
    :return: The augmentation-stage output to write to S3.
    """
    original_eicr_id = augmenter_input.original_eicr_id

    if augmenter_input.passthrough_reason is not None:
        return _build_original_eicr_output(
            persistence_id=persistence_id,
            original_eicr_id=original_eicr_id or CdaInstanceIdentifier(null_flavor="NI"),
            original_eicr=original_eicr,
            passthrough_reason=augmenter_input.passthrough_reason,
        )

    try:
        augmenter = EICRAugmenter(
            document=original_eicr,
            nonstandard_codes=augmenter_input.nonstandard_codes,
            deterministic_id_seed=augmenter_input.persistence_id,
        )

        if original_eicr_id is None:
            original_eicr_id = augmenter.original_eicr_id

        output = _build_augmented_eicr_output(
            persistence_id=persistence_id,
            augmenter=augmenter,
        )
    except Exception as e:
        if original_eicr_id is None:
            logger.exception(
                "Augmentation failed before original eICR ID could be resolved",
                status="error",
                passthrough_reason=PassthroughReason.AUGMENTATION_EXCEPTION,
            )
            raise

        logger.exception(
            "Augmentation failed; writing original eICR output",
            status="passthrough",
            passthrough_reason=PassthroughReason.AUGMENTATION_EXCEPTION,
        )
        return _build_original_eicr_output(
            persistence_id=persistence_id,
            original_eicr_id=original_eicr_id,
            original_eicr=original_eicr,
            error=str(e),
            passthrough_reason=PassthroughReason.AUGMENTATION_EXCEPTION,
        )

    validation_error = _introduced_validation_error(original_eicr, output.augmented_eicr)

    if validation_error:
        return _build_original_eicr_output(
            persistence_id=persistence_id,
            original_eicr_id=output.metadata.original_eicr_id,
            original_eicr=original_eicr,
            nonstandard_codes=output.metadata.nonstandard_codes,
            error=validation_error,
            passthrough_reason=PassthroughReason.AUGMENTATION_VALIDATION_FAILURE,
        )

    return output


def _build_original_eicr_output(  # noqa: PLR0913
    persistence_id: str,
    original_eicr_id: CdaInstanceIdentifier,
    original_eicr: str,
    passthrough_reason: PassthroughReason | None,
    nonstandard_codes: list[NonstandardCodeInstanceMetadata] | None = None,
    error: str | None = None,
) -> TTCAugmenterOutput:
    """Build output for cases where the augmentation stage emits the original eICR.

    This is the only place that intentionally sets augmented_eicr_id to
    original_eicr_id. That assignment is correct only because the XML being
    written as the augmentation-stage output is the original eICR, not a newly
    augmented document.

    :param persistence_id: The stable pipeline/storage ID used for S3 keys.
    :param original_eicr_id: The CDA document ID from the original eICR.
    :param original_eicr: The original eICR XML string.
    :param passthrough_reason: The reason the original eICR is being emitted.
    :param nonstandard_codes: Metadata for nonstandard codes attempted before fallback.
    :param error: The error that caused fallback, if any.
    :return: The augmentation-stage output containing the original eICR.
    """
    if nonstandard_codes is None:
        nonstandard_codes = []

    metadata = Metadata(
        original_eicr_id=original_eicr_id,
        augmented_eicr_id=original_eicr_id,
        nonstandard_codes=nonstandard_codes,
        error=error,
        passthrough_reason=passthrough_reason,
    )

    return TTCAugmenterOutput(
        persistence_id=persistence_id,
        augmented_eicr=original_eicr,
        metadata=metadata,
    )


def _build_augmented_eicr_output(
    persistence_id: str,
    augmenter: EICRAugmenter,
) -> TTCAugmenterOutput:
    """Build output for cases where the augmentation stage emits a new eICR.

    Successful augmentation must use Metadata returned by EICRAugmenter.augment()
    because that is where the new augmented_eicr_id is created.

    :param persistence_id: The stable pipeline/storage ID used for S3 keys.
    :param augmenter: The initialized EICRAugmenter for the original eICR.
    :return: The augmentation-stage output containing the augmented eICR.
    """
    result = augmenter.augment()

    return TTCAugmenterOutput(
        persistence_id=persistence_id,
        augmented_eicr=result.augmented_xml,
        metadata=result.metadata,
    )


def _load_ttc_output(persistence_id: str, bucket_name: str) -> TTCAugmenterInput:
    """Load TTC output from S3.

    :param persistence_id: The persistence ID for the S3 object key.
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
        bucket_name=bucket_name, object_key=object_key
    )
    return TTCAugmenterInput.model_validate_json(content)


def _load_original_eicr(persistence_id: str, bucket_name: str) -> str:
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
    return lambda_handler.get_file_content_from_s3(bucket_name=bucket_name, object_key=object_key)


def _save_augmentation_outputs(
    persistence_id: str,
    output: TTCAugmenterOutput,
    bucket_name: str,
) -> None:
    """Save augmented eICR and metadata to S3.

    :param persistence_id: The persistence ID for the S3 object key.
    :param output: The augmentation output containing the augmented eICR and metadata.
    :param bucket_name: The S3 bucket name to write to.
    """
    augmented_eicr_key = f"{AUGMENTED_EICR_PREFIX}{persistence_id}"
    augmentation_metadata_key = f"{AUGMENTATION_METADATA_PREFIX}{persistence_id}"

    lambda_handler.put_file(
        file_obj=io.BytesIO(output.augmented_eicr.encode("utf-8")),
        bucket_name=bucket_name,
        object_key=augmented_eicr_key,
    )
    logger.info(
        "Saved augmented eICR to S3",
        bucket_name=bucket_name,
        s3_key=augmented_eicr_key,
        status="success",
        passthrough_reason=output.metadata.passthrough_reason,
    )

    lambda_handler.put_file(
        file_obj=io.BytesIO(output.metadata.model_dump_json().encode("utf-8")),
        bucket_name=bucket_name,
        object_key=augmentation_metadata_key,
    )

    logger.info(
        "Saved augmentation metadata to S3",
        bucket_name=bucket_name,
        s3_key=augmentation_metadata_key,
        status="success",
        passthrough_reason=output.metadata.passthrough_reason,
    )
