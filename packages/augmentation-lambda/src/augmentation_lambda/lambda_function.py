import io
import json
import os
from typing import TypedDict

from aws_lambda_powertools.utilities.data_classes import SQSEvent
from aws_lambda_powertools.utilities.data_classes import event_source
from aws_lambda_powertools.utilities.typing import LambdaContext
from botocore.client import BaseClient

import lambda_handler
from augmentation.models import TTCAugmenterConfig
from augmentation.models.application import TTCAugmenterOutput
from augmentation.services.eicr_augmenter import EICRAugmenter
from shared_models import AUGMENTATION_METADATA_PREFIX
from shared_models import AUGMENTED_EICR_PREFIX
from shared_models import EICR_INPUT_PREFIX
from shared_models import S3_BUCKET
from shared_models import TTC_OUTPUT_PREFIX
from shared_models import TTCOutput

# Environment variables
_S3_BUCKET = os.getenv("S3_BUCKET", S3_BUCKET)
_AUGMENTED_EICR_PREFIX = os.getenv("AUGMENTED_EICR_PREFIX", AUGMENTED_EICR_PREFIX)
_AUGMENTATION_METADATA_PREFIX = os.getenv(
    "AUGMENTATION_METADATA_PREFIX", AUGMENTATION_METADATA_PREFIX
)

# Cache S3 client to reuse across Lambda invocations
_cached_s3_client: BaseClient | None = None


class HandlerResponse(TypedDict):
    """Response from the AWS Lambda handler."""

    results: list[dict[str, object]]
    batchItemFailures: list[dict[str, str]]


@event_source(data_class=SQSEvent)
def handler(event: SQSEvent, context: LambdaContext) -> HandlerResponse:
    """AWS Lambda handler for augmenting eICRs with nonstandard codes.

    :param event: The SQS event containing messages with eICRs to augment.
    :param context: The AWS Lambda context object.
    :return: A dictionary containing the results of the augmentation and any batch item failures.
    """
    global _cached_s3_client  # noqa: PLW0603

    if _cached_s3_client is None:
        _cached_s3_client = lambda_handler.create_s3_client()
    s3_client = _cached_s3_client

    results: list[dict[str, object]] = []
    batch_item_failures: list[dict[str, str]] = []

    for record in event.records:
        message_id = record["messageId"]

        try:
            s3_event = json.loads(record.body)

            eventbridge_data = lambda_handler.get_eventbridge_data_from_s3_event(s3_event)
            object_key = eventbridge_data["object_key"]
            persistence_id = lambda_handler.get_persistence_id(object_key, TTC_OUTPUT_PREFIX)

            config = TTCAugmenterConfig()

            object_key = f"{EICR_INPUT_PREFIX}{persistence_id}"
            original_eicr_content = lambda_handler.get_file_content_from_s3(
                bucket_name=_S3_BUCKET, object_key=object_key, s3_client=s3_client
            )

            object_key = f"{TTC_OUTPUT_PREFIX}{persistence_id}"
            ttc_output = json.loads(
                lambda_handler.get_file_content_from_s3_to_json(
                    bucket_name=_S3_BUCKET, object_key=object_key, s3_client=s3_client
                )
            )
            ttc_output = TTCOutput(**ttc_output)

            # TODO: in the future, when there are multiple applications using the augmentation service, we will need to determine which augmenter to use based on the application code in the config. For now, since TTC is the only application, we can directly initialize the EICRAugmenter.
            augmenter = EICRAugmenter(
                document=original_eicr_content,
                nonstandard_codes=ttc_output.nonstandard_codes,
                config=config,
            )

            metadata = augmenter.augment()

            # TODO: the output of the augmenter will likely need to be modified when there are multiple applications and augmenters, but for now we can directly create a TTC augmenter output.
            output = TTCAugmenterOutput(
                eicr_id=persistence_id,
                augmented_eicr=augmenter.augmented_xml,
                metadata=metadata,
            )

            # Save augmented eICR and metadata to S3
            _save_augmentation_outputs(persistence_id, output, s3_client)

            results.append(
                {
                    "messageId": message_id,
                    "status": "success",
                    "result": output.model_dump(),
                }
            )
        except Exception as exc:
            batch_item_failures.append({"itemIdentifier": message_id})
            results.append(
                {
                    "messageId": message_id,
                    "status": "error",
                    "error": str(exc),
                }
            )

    return {
        "results": results,
        "batchItemFailures": batch_item_failures,
    }


def _save_augmentation_outputs(
    eicr_id: str, output: TTCAugmenterOutput, s3_client: BaseClient
) -> None:
    """Save augmented eICR and metadata to S3.

    :param eicr_id: The eICR identifier.
    :param output: The augmentation output containing the augmented eICR and metadata.
    :param s3_client: The S3 client to use for uploading files.
    """
    lambda_handler.put_file(
        file_obj=io.BytesIO(output.augmented_eicr.encode("utf-8")),
        bucket_name=_S3_BUCKET,
        object_key=f"{_AUGMENTED_EICR_PREFIX}{eicr_id}",
        s3_client=s3_client,
    )
    lambda_handler.put_file(
        file_obj=io.BytesIO(output.metadata.model_dump_json().encode("utf-8")),
        bucket_name=_S3_BUCKET,
        object_key=f"{_AUGMENTATION_METADATA_PREFIX}{eicr_id}",
        s3_client=s3_client,
    )
