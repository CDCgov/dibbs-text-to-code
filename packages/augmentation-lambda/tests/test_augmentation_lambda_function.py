import json
from datetime import datetime
from uuid import UUID
from zoneinfo import ZoneInfo

import pytest
import time_machine
from pytest_mock import MockerFixture
from pytest_snapshot.plugin import Snapshot

import lambda_handler
from augmentation_lambda import lambda_function

S3_BUCKET = "dibbs-text-to-code"
TTC_OUTPUT_PREFIX = "TTCAugmentationMetadataV2/"
AUGMENTED_EICR_PREFIX = "AugmentationEICRV2/"
AUGMENTATION_METADATA_PREFIX = "AugmentationMetadataV2/"
TEST_PERSISTENCE_ID = "2025/09/03/1-5f84c7a5-91d7f5c6a2b7c9e08f0d1234"
SUCCESS_CODE = 200


def _serialize_snapshot_value(value: dict[str, object]) -> str:
    normalized = json.loads(json.dumps(value))
    return json.dumps(normalized, indent=2, sort_keys=True)


def _build_sqs_record(body: str, message_id: str, receipt_handle: str) -> dict[str, object]:
    return {
        "messageId": message_id,
        "receiptHandle": receipt_handle,
        "body": body,
        "attributes": {
            "ApproximateReceiveCount": "1",
            "SentTimestamp": "1752691260451",
            "SenderId": "AIDAJXNJGGKNS7OSV23OI",
            "ApproximateFirstReceiveTimestamp": "1752691260458",
        },
        "messageAttributes": {},
        "md5OfBody": "dummy-md5",
        "eventSource": "aws:sqs",
        "eventSourceARN": "arn:aws:sqs:us-east-1:123456789012:queue-name",
        "awsRegion": "us-east-1",
    }


def _build_sqs_event_from_payloads(
    payloads: list[dict[str, object]],
    message_ids: list[str],
) -> dict[str, object]:
    return {
        "Records": [
            _build_sqs_record(
                body=json.dumps(payload),
                message_id=message_id,
                receipt_handle=f"test-receipt-handle-{index}",
            )
            for index, (payload, message_id) in enumerate(zip(payloads, message_ids, strict=True))
        ]
    }


def _build_empty_body_event() -> dict[str, object]:
    return {
        "Records": [
            _build_sqs_record(
                body="",
                message_id="msg-empty-body",
                receipt_handle="test-receipt-handle",
            )
        ]
    }


@pytest.fixture(autouse=False)
def mock_augmented_ids(mocker: MockerFixture) -> None:
    doc_id = UUID("12345678-1234-5678-1234-567812345678")
    set_id = UUID("87654321-4321-8765-4321-876543218765")
    mocker.patch("augmentation.services.eicr_augmenter.uuid4", side_effect=[doc_id, set_id])


class TestHandler:
    """Tests for the augmentation Lambda handler."""

    def test_handler_writes_outputs_to_s3(
        self,
        example_sqs_event,
        mock_aws_setup,
        mocker: MockerFixture,
        snapshot: Snapshot,
        mock_augmented_ids,
    ) -> None:

        with time_machine.travel(
            datetime(2026, 2, 13, 15, 27, 57, tzinfo=ZoneInfo("America/New_York")), tick=False
        ):
            result = lambda_function.handler(example_sqs_event, None)

        # Assert handler function returns expected values
        assert result["statusCode"] == SUCCESS_CODE
        assert result["message"] == "Augmentation processed successfully!"
        assert result["num_success_eicrs"] == 1

        # Verify augmented eICR was written
        augmented_eicr = lambda_handler.get_file_content_from_s3(
            bucket_name=S3_BUCKET,
            object_key=f"{AUGMENTED_EICR_PREFIX}{TEST_PERSISTENCE_ID}",
            s3_client=mock_aws_setup,
        )
        snapshot.assert_match(augmented_eicr, "handler_writes_outputs_augmented_eicr.xml")

        # Verify metadata was written
        metadata_raw = lambda_handler.get_file_content_from_s3(
            bucket_name=S3_BUCKET,
            object_key=f"{AUGMENTATION_METADATA_PREFIX}{TEST_PERSISTENCE_ID}",
            s3_client=mock_aws_setup,
        )
        metadata = json.loads(metadata_raw)
        snapshot.assert_match(
            _serialize_snapshot_value(metadata),
            "handler_writes_outputs_metadata.json",
        )

        # Validate augmented eICR

    def test_handler_source_bucket_routing(
        self,
        example_s3_event_payload,
        mock_aws_setup,
        mocker: MockerFixture,
        snapshot: Snapshot,
        mock_augmented_ids,
    ) -> None:
        """Verify bucket name is extracted from the S3 event, not the env var."""
        custom_bucket = "custom-bucket"

        # Create the custom bucket and populate it with the same test data
        mock_aws_setup.create_bucket(Bucket=custom_bucket)
        # Copy eICR to custom bucket
        eicr_obj = mock_aws_setup.get_object(
            Bucket=S3_BUCKET,
            Key=f"TextToCodeSubmissionV2/{TEST_PERSISTENCE_ID}",
        )
        mock_aws_setup.put_object(
            Bucket=custom_bucket,
            Key=f"TextToCodeSubmissionV2/{TEST_PERSISTENCE_ID}",
            Body=eicr_obj["Body"].read(),
        )
        # Copy TTC output to custom bucket
        ttc_obj = mock_aws_setup.get_object(
            Bucket=S3_BUCKET,
            Key=f"{TTC_OUTPUT_PREFIX}{TEST_PERSISTENCE_ID}",
        )
        mock_aws_setup.put_object(
            Bucket=custom_bucket,
            Key=f"{TTC_OUTPUT_PREFIX}{TEST_PERSISTENCE_ID}",
            Body=ttc_obj["Body"].read(),
        )

        # Modify the event to use custom bucket
        example_s3_event_payload["detail"]["bucket"]["name"] = custom_bucket
        event = _build_sqs_event_from_payloads(
            payloads=[example_s3_event_payload],
            message_ids=["msg-routing"],
        )
        snapshot.assert_match(
            _serialize_snapshot_value(event),
            "handler_source_bucket_routing_event.json",
        )

        with time_machine.travel(
            datetime(2026, 2, 13, 15, 27, 57, tzinfo=ZoneInfo("America/New_York")), tick=False
        ):
            result = lambda_function.handler(event, None)
        snapshot.assert_match(
            _serialize_snapshot_value(result),
            "handler_source_bucket_routing_result.json",
        )

        augmented_eicr = lambda_handler.get_file_content_from_s3(
            bucket_name=custom_bucket,
            object_key=f"{AUGMENTED_EICR_PREFIX}{TEST_PERSISTENCE_ID}",
            s3_client=mock_aws_setup,
        )
        snapshot.assert_match(
            augmented_eicr,
            "handler_source_bucket_routing_augmented_eicr.xml",
        )

    def test_handler_error_missing_eicr(
        self, example_s3_event_payload, mock_aws_setup, snapshot: Snapshot
    ) -> None:
        """Test error when the original eICR is not found in S3."""
        # Remove the eICR from S3
        mock_aws_setup.delete_object(
            Bucket=S3_BUCKET,
            Key=f"TextToCodeSubmissionV2/{TEST_PERSISTENCE_ID}",
        )

        event = _build_sqs_event_from_payloads(
            payloads=[example_s3_event_payload],
            message_ids=["msg-missing-eicr"],
        )
        snapshot.assert_match(
            _serialize_snapshot_value(event),
            "handler_error_missing_eicr_event.json",
        )

        result = lambda_function.handler(event, None)

        assert result["num_failure_eicrs"] == 1
        assert len(result["failures"]) == 1
        snapshot.assert_match(
            _serialize_snapshot_value(result),
            "handler_error_missing_eicr_result.json",
        )

    def test_handler_error_missing_ttc_output(
        self, example_s3_event_payload, mock_aws_setup, snapshot: Snapshot
    ) -> None:
        """Test error when the TTC output is not found in S3."""
        mock_aws_setup.delete_object(
            Bucket=S3_BUCKET,
            Key=f"{TTC_OUTPUT_PREFIX}{TEST_PERSISTENCE_ID}",
        )

        event = _build_sqs_event_from_payloads(
            payloads=[example_s3_event_payload],
            message_ids=["msg-missing-ttc"],
        )
        snapshot.assert_match(
            _serialize_snapshot_value(event),
            "handler_error_missing_ttc_output_event.json",
        )

        result = lambda_function.handler(event, None)

        assert result["num_failure_eicrs"] == 1
        assert len(result["failures"]) == 1
        snapshot.assert_match(
            _serialize_snapshot_value(result),
            "handler_error_missing_ttc_output_result.json",
        )

    def test_handler_mixed_batch_results(
        self, example_s3_event_payload, mock_aws_setup, snapshot: Snapshot
    ) -> None:
        """Test batch with both success and failure records."""
        # Create a second event pointing to a non-existent persistence ID
        bad_event_payload = example_s3_event_payload.copy()
        bad_event_payload = json.loads(json.dumps(example_s3_event_payload))
        bad_event_payload["detail"]["object"]["key"] = f"{TTC_OUTPUT_PREFIX}nonexistent/id"

        event = _build_sqs_event_from_payloads(
            payloads=[example_s3_event_payload, bad_event_payload],
            message_ids=["msg-success", "msg-fail"],
        )
        snapshot.assert_match(
            _serialize_snapshot_value(event),
            "handler_mixed_batch_results_event.json",
        )

        result = lambda_function.handler(event, None)

        assert result["num_success_eicrs"] == 1
        assert result["num_failure_eicrs"] == 1
        snapshot.assert_match(
            _serialize_snapshot_value(result),
            "handler_mixed_batch_results_result.json",
        )

    def test_handler_skips_empty_sqs_body(self, mock_aws_setup) -> None:
        event = _build_empty_body_event()

        result = lambda_function.handler(event, None)

        assert result["statusCode"] == SUCCESS_CODE
        assert result["message"] == "Augmentation processed successfully!"
        assert result["num_success_eicrs"] == 1
