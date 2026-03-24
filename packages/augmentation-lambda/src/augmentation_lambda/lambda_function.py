import json
from typing import TypedDict

from aws_lambda_typing import context as lambda_context
from aws_lambda_typing import events as lambda_events

from augmentation.models import TTCAugmenterConfig
from augmentation.models.application import TTCAugmenterOutput
from augmentation.services.eicr_augmenter import EICRAugmenter
from shared_models import TTCAugmenterInput


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
