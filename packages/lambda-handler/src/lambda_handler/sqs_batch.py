"""Shared SQS batch-processing envelope for the pipeline lambdas.

Both SQS-triggered lambdas (augmentation and TTC) process a batch of records
that each wrap an EventBridge S3 event, accumulate per-record outcomes, and
return the same response shape (``batchItemFailures`` plus success/failure
summaries). This module owns that envelope so the lambdas only supply their
record-processing logic.
"""

import json
from collections.abc import Callable
from dataclasses import dataclass

from aws_lambda_powertools import Logger
from aws_lambda_powertools.utilities.data_classes import SQSEvent
from aws_lambda_powertools.utilities.data_classes.sqs_event import SQSRecord

from .lambda_handler import get_eventbridge_data_from_s3_event, get_persistence_id


@dataclass(frozen=True)
class ParsedS3Record:
    """The S3 object coordinates unwrapped from an SQS record's EventBridge event."""

    persistence_id: str
    object_key: str
    bucket_name: str | None


def parse_s3_sqs_record(
    record: SQSRecord,
    input_prefix: str,
    logger: Logger,
    default_bucket: str | None = None,
) -> ParsedS3Record | None:
    """Unwrap the EventBridge S3 event carried in an SQS record's body.

    :param record: The SQS record with an EventBridge S3 event in the body.
    :param input_prefix: The pipeline-step prefix to strip from the object key.
    :param logger: The calling lambda's logger.
    :param default_bucket: Bucket to fall back to when the event omits one. When
        ``None``, ``bucket_name`` on the result may be ``None`` and the caller
        decides how to handle it.
    :return: The parsed record, or ``None`` when the SQS body is empty.
    """
    if not record.body:
        logger.warning("Empty SQS body", message_id=record.message_id, status="skipped")
        return None

    s3_event = json.loads(record.body)
    eventbridge_data = get_eventbridge_data_from_s3_event(s3_event)
    object_key = eventbridge_data["object_key"]
    bucket_name = eventbridge_data.get("bucket_name") or default_bucket

    return ParsedS3Record(
        persistence_id=get_persistence_id(object_key, input_prefix),
        object_key=object_key,
        bucket_name=bucket_name,
    )


@dataclass(frozen=True)
class SqsBatchProcessor[T]:
    """A lambda's SQS batch envelope: its record processing plus the shared accounting.

    ``run`` processes every record in an SQS event and builds the standard
    batch response. Each record outcome is one of: ``skipped``
    (``process_record`` returned ``None``), ``passthrough_written``
    (``is_passthrough`` on the output, or a successful ``on_error`` recovery),
    or ``processed``. A record whose processing raises is recorded in
    ``failures`` and, unless ``on_error`` wrote a passthrough for it, in
    ``batchItemFailures`` so SQS retries it.
    """

    process_record: Callable[[SQSRecord], T | None]
    """Processes one record; returns ``None`` to skip it."""

    is_passthrough: Callable[[T], bool]
    """Whether a record's output is a passthrough result."""

    completion_message: str
    """The invocation-completed log/response message."""

    logger: Logger
    """The calling lambda's logger."""

    on_error: Callable[[SQSRecord, Exception], bool] | None = None
    """Handles a record's exception and returns whether a passthrough output
    was written; ``None`` to always retry via SQS."""

    def run(self, event: SQSEvent) -> dict:
        """Process every record in the SQS batch and build the standard response.

        :param event: The SQS event containing the records to process.
        :return: The batch response, including ``batchItemFailures``.
        """
        batch_item_failures: list[dict[str, str]] = []
        failures: list[dict[str, object]] = []
        successes: list[dict[str, str]] = []

        for record in event.records:
            try:
                output = self.process_record(record)

                if output is None:
                    record_status = "skipped"
                elif self.is_passthrough(output):
                    record_status = "passthrough_written"
                else:
                    record_status = "processed"
                successes.append({"message_id": record.message_id, "status": record_status})
            except Exception as e:
                self.logger.exception(
                    "Error processing record",
                    error=str(e),
                    message_id=record.message_id,
                    status="error",
                )
                passthrough_written = self.on_error(record, e) if self.on_error else False
                failures.append(
                    {
                        "error": str(e),
                        "error_type": type(e).__name__,
                        "message_id": record.message_id,
                        "passthrough_written": passthrough_written,
                        "sqs_retry": not passthrough_written,
                    }
                )

                if passthrough_written:
                    successes.append(
                        {
                            "message_id": record.message_id,
                            "status": "passthrough_written",
                        }
                    )
                else:
                    batch_item_failures.append({"itemIdentifier": record.message_id})

        if batch_item_failures:
            status = "partial_failure"
        elif any(success["status"] == "passthrough_written" for success in successes):
            status = "success_with_passthrough"
        else:
            status = "success"

        response: dict[str, object] = {
            "batchItemFailures": batch_item_failures,
            "failures": failures,
            "message": self.completion_message,
            "num_failure_eicrs": len(batch_item_failures),
            "num_processing_error_eicrs": len(failures),
            "num_success_eicrs": len(successes),
            "status": status,
            "successes": successes,
        }

        self.logger.info(
            self.completion_message,
            batch_item_failures=batch_item_failures,
            failures=failures,
            num_failure_eicrs=len(batch_item_failures),
            num_processing_error_eicrs=len(failures),
            num_success_eicrs=len(successes),
            status=status,
            successes=successes,
        )

        return response
