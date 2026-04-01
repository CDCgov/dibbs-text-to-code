import io
import json
import os
from typing import TypedDict

from aws_lambda_typing import context as lambda_context
from aws_lambda_typing import events as lambda_events

import lambda_handler
from augmentation.models import TTCAugmenterConfig
from botocore.client import BaseClient
from augmentation.models.application import TTCAugmenterOutput
from augmentation.services.eicr_augmenter import EICRAugmenter
from shared_models import TTCAugmenterInput

# Environment variables
S3_BUCKET = os.getenv("S3_BUCKET", "dibbs-text-to-code")
AUGMENTED_EICR_PREFIX = os.getenv("AUGMENTED_EICR_PREFIX", "AugmentationEICRV2/")
AUGMENTATION_METADATA_PREFIX = os.getenv("AUGMENTATION_METADATA_PREFIX", "AugmentationMetadataV2/")

# Cache S3 client to reuse across Lambda invocations
_cached_s3_client: BaseClient | None = None


class HandlerResponse(TypedDict):
    """Response from the AWS Lambda handler."""

    results: list[dict[str, object]]
    batchItemFailures: list[dict[str, str]]


def handler(event: lambda_events.SQSEvent, context: lambda_context.Context) -> HandlerResponse:
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

    for record in event["Records"]:
        message_id = record["messageId"]

        try:
            payload = json.loads(record["body"])
            augmenter_input = TTCAugmenterInput.model_validate(
                {
                    "eicr_id": payload["eicr_id"],
                    "nonstandard_codes": payload["nonstandard_codes"],
                }
            )

            eicr = payload["eicr"]

            # TODO: will need to determine config based on application code when there are multiple applications using the augmentation service. For now, since TTC is the only application, we can directly initialize the config as a TTC config.
            config = (
                TTCAugmenterConfig.model_validate(payload["config"])
                if "config" in payload
                else TTCAugmenterConfig()
            )

            # TODO: in the future, when there are multiple applications using the augmentation service, we will need to determine which augmenter to use based on the application code in the config. For now, since TTC is the only application, we can directly initialize the EICRAugmenter.
            augmenter = EICRAugmenter(
                document=eicr,
                nonstandard_codes=augmenter_input.nonstandard_codes,
                config=config,
            )

            metadata = augmenter.augment()

            # TODO: the output of the augmenter will likely need to be modified when there are multiple applications and augmenters, but for now we can directly create a TTC augmenter output.
            output = TTCAugmenterOutput(
                eicr_id=augmenter_input.eicr_id,
                augmented_eicr=augmenter.augmented_xml,
                metadata=metadata,
            )

            # Save augmented eICR and metadata to S3
            _save_augmentation_outputs(augmenter_input.eicr_id, output, s3_client)

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
        bucket_name=S3_BUCKET,
        object_key=f"{AUGMENTED_EICR_PREFIX}{eicr_id}",
        s3_client=s3_client,
    )
    lambda_handler.put_file(
        file_obj=io.BytesIO(output.metadata.model_dump_json().encode("utf-8")),
        bucket_name=S3_BUCKET,
        object_key=f"{AUGMENTATION_METADATA_PREFIX}{eicr_id}",
        s3_client=s3_client,
    )
