import json
import os
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
import time_machine
from pytest_snapshot.plugin import Snapshot

import lambda_handler
from augmentation.models import Metadata
from augmentation_lambda import lambda_function
from shared_models import CdaInstanceIdentifier, PassthroughReason, TTCAugmenterInput
from validation import ValidationResult, validate_eicr

S3_BUCKET = os.environ["S3_BUCKET"]
TTC_OUTPUT_PREFIX = os.environ["TTC_OUTPUT_PREFIX"]
AUGMENTED_EICR_PREFIX = os.environ["AUGMENTED_EICR_PREFIX"]
AUGMENTATION_METADATA_PREFIX = os.environ["AUGMENTATION_METADATA_PREFIX"]
TEST_PERSISTENCE_ID = os.environ["TEST_PERSISTENCE_ID"]
SUCCESS_CODE = 200
# The diff-based gate validates the augmented eICR, then the original as a baseline.
EXPECTED_DIFF_VALIDATION_CALLS = 2
EXPECTED_ORIGINAL_EICR_ID = CdaInstanceIdentifier(
    root="c8516bdc-8bb2-40aa-8dae-20a77546488f", extension=None
)
EXPECTED_AUGMENTED_EICR_ID = CdaInstanceIdentifier(
    root="d44dc1c6-8a0c-5236-906e-12f6475589ec", extension=None
)


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


class TestHandler:
    """Tests for the augmentation Lambda handler."""

    def test_handler_success(
        self,
        example_sqs_event,
        mock_aws_setup,
        snapshot: Snapshot,
        mock_lambda_context,
    ) -> None:

        with time_machine.travel(
            datetime(2026, 2, 13, 15, 27, 57, tzinfo=ZoneInfo("America/New_York")), tick=False
        ):
            result = lambda_function.handler(example_sqs_event, mock_lambda_context)

        # Assert handler function returns expected values
        assert result["statusCode"] == SUCCESS_CODE
        assert result["message"] == "Augmentation processed successfully!"
        assert result["num_success_eicrs"] == 1

        # Verify augmented eICR was written
        augmented_eicr = lambda_handler.get_file_content_from_s3(
            bucket_name=S3_BUCKET,
            object_key=f"{AUGMENTED_EICR_PREFIX}{TEST_PERSISTENCE_ID}",
        )
        snapshot.assert_match(augmented_eicr, "handler_writes_outputs_augmented_eicr.xml")

        # Verify metadata was written
        metadata_raw = lambda_handler.get_file_content_from_s3(
            bucket_name=S3_BUCKET,
            object_key=f"{AUGMENTATION_METADATA_PREFIX}{TEST_PERSISTENCE_ID}",
        )
        metadata = Metadata.model_validate_json(metadata_raw)
        assert metadata.original_eicr_id == EXPECTED_ORIGINAL_EICR_ID
        assert metadata.augmented_eicr_id == EXPECTED_AUGMENTED_EICR_ID
        assert metadata.augmented_eicr_id != metadata.original_eicr_id
        assert metadata.augmented_eicr_id.root != TEST_PERSISTENCE_ID
        assert metadata.augmented_eicr_id.extension != TEST_PERSISTENCE_ID
        assert metadata.passthrough_reason is None
        snapshot.assert_match(
            _serialize_snapshot_value(metadata.model_dump(mode="json")),
            "handler_writes_outputs_metadata.json",
        )

        # Validate augmented eICR
        actual_validation_results = validate_eicr(augmented_eicr)
        assert actual_validation_results == []  # Empty list means no errors.

    def test_handler_writes_original_eicr_when_ttc_output_has_passthrough_reason(
        self, example_sqs_event, mock_aws_setup, mocker, mock_lambda_context, snapshot
    ) -> None:
        original_eicr = lambda_handler.get_file_content_from_s3(
            bucket_name=S3_BUCKET,
            object_key=f"TextToCodeSubmissionV2/{TEST_PERSISTENCE_ID}",
        )

        ttc_output = TTCAugmenterInput.model_validate(
            json.loads(
                lambda_handler.get_file_content_from_s3(
                    bucket_name=S3_BUCKET,
                    object_key=f"{TTC_OUTPUT_PREFIX}{TEST_PERSISTENCE_ID}",
                )
            )
        ).model_copy(
            update={
                "original_eicr_id": CdaInstanceIdentifier(root=EXPECTED_ORIGINAL_EICR_ID.root),
                "passthrough_reason": PassthroughReason.NO_CODE_MATCHES,
            }
        )

        mock_aws_setup.put_object(
            Bucket=S3_BUCKET,
            Key=f"{TTC_OUTPUT_PREFIX}{TEST_PERSISTENCE_ID}",
            Body=ttc_output.model_dump_json().encode("utf-8"),
        )

        augmenter_mock = mocker.patch("augmentation_lambda.lambda_function.EICRAugmenter")

        result = lambda_function.handler(example_sqs_event, mock_lambda_context)

        assert result["statusCode"] == SUCCESS_CODE
        assert result["message"] == "Augmentation processed successfully!"
        assert result["num_success_eicrs"] == 1
        augmenter_mock.assert_not_called()

        augmented_eicr = lambda_handler.get_file_content_from_s3(
            bucket_name=S3_BUCKET,
            object_key=f"{AUGMENTED_EICR_PREFIX}{TEST_PERSISTENCE_ID}",
        )
        assert augmented_eicr == original_eicr

        metadata_raw = lambda_handler.get_file_content_from_s3(
            bucket_name=S3_BUCKET,
            object_key=f"{AUGMENTATION_METADATA_PREFIX}{TEST_PERSISTENCE_ID}",
        )
        metadata = Metadata.model_validate_json(metadata_raw)
        assert metadata.original_eicr_id == EXPECTED_ORIGINAL_EICR_ID
        assert metadata.augmented_eicr_id == EXPECTED_ORIGINAL_EICR_ID
        assert metadata.original_eicr_id.root != TEST_PERSISTENCE_ID
        assert metadata.original_eicr_id.extension != TEST_PERSISTENCE_ID
        assert metadata.augmented_eicr_id.root != TEST_PERSISTENCE_ID
        assert metadata.augmented_eicr_id.extension != TEST_PERSISTENCE_ID
        assert metadata.passthrough_reason == PassthroughReason.NO_CODE_MATCHES
        snapshot.assert_match(
            _serialize_snapshot_value(metadata.model_dump(mode="json")),
            "ttc_passthrough.json",
        )

    def test_handler_writes_augmented_eicr_when_ttc_output_passthrough_reason_is_missing(
        self, example_sqs_event, mock_aws_setup, mock_lambda_context
    ) -> None:
        ttc_output = TTCAugmenterInput.model_validate(
            json.loads(
                lambda_handler.get_file_content_from_s3(
                    bucket_name=S3_BUCKET,
                    object_key=f"{TTC_OUTPUT_PREFIX}{TEST_PERSISTENCE_ID}",
                )
            )
        ).model_copy(
            update={
                "original_eicr_id": CdaInstanceIdentifier(root=EXPECTED_ORIGINAL_EICR_ID.root),
                "passthrough_reason": None,
            }
        )
        ttc_output_json = json.loads(ttc_output.model_dump_json())
        ttc_output_json.pop("passthrough_reason", None)

        mock_aws_setup.put_object(
            Bucket=S3_BUCKET,
            Key=f"{TTC_OUTPUT_PREFIX}{TEST_PERSISTENCE_ID}",
            Body=json.dumps(ttc_output_json).encode("utf-8"),
        )

        result = lambda_function.handler(example_sqs_event, mock_lambda_context)

        assert result["statusCode"] == SUCCESS_CODE
        assert result["message"] == "Augmentation processed successfully!"
        assert result["num_success_eicrs"] == 1

        augmented_eicr = lambda_handler.get_file_content_from_s3(
            bucket_name=S3_BUCKET,
            object_key=f"{AUGMENTED_EICR_PREFIX}{TEST_PERSISTENCE_ID}",
        )

        metadata_raw = lambda_handler.get_file_content_from_s3(
            bucket_name=S3_BUCKET,
            object_key=f"{AUGMENTATION_METADATA_PREFIX}{TEST_PERSISTENCE_ID}",
        )
        metadata = Metadata.model_validate_json(metadata_raw)
        assert metadata.original_eicr_id == EXPECTED_ORIGINAL_EICR_ID
        assert metadata.augmented_eicr_id == EXPECTED_AUGMENTED_EICR_ID
        assert metadata.augmented_eicr_id != metadata.original_eicr_id
        assert metadata.augmented_eicr_id.root != TEST_PERSISTENCE_ID
        assert metadata.augmented_eicr_id.extension != TEST_PERSISTENCE_ID
        assert metadata.passthrough_reason is None

        actual_validation_results = validate_eicr(augmented_eicr)
        assert actual_validation_results == []

    def test_handler_writes_original_eicr_when_augmentation_fails(
        self, example_sqs_event, mock_aws_setup, mocker, mock_lambda_context, snapshot
    ) -> None:
        original_eicr = lambda_handler.get_file_content_from_s3(
            bucket_name=S3_BUCKET,
            object_key=f"TextToCodeSubmissionV2/{TEST_PERSISTENCE_ID}",
        )

        augmenter = mocker.Mock()
        augmenter.original_eicr_id = EXPECTED_ORIGINAL_EICR_ID
        augmenter.augment.side_effect = Exception("augmentation boom")

        mocker.patch(
            "augmentation_lambda.lambda_function.EICRAugmenter",
            return_value=augmenter,
        )

        result = lambda_function.handler(example_sqs_event, mock_lambda_context)

        assert result["statusCode"] == SUCCESS_CODE
        assert result["message"] == "Augmentation processed successfully!"
        assert result["num_success_eicrs"] == 1

        augmented_eicr = lambda_handler.get_file_content_from_s3(
            bucket_name=S3_BUCKET,
            object_key=f"{AUGMENTED_EICR_PREFIX}{TEST_PERSISTENCE_ID}",
        )
        assert augmented_eicr == original_eicr

        metadata_raw = lambda_handler.get_file_content_from_s3(
            bucket_name=S3_BUCKET,
            object_key=f"{AUGMENTATION_METADATA_PREFIX}{TEST_PERSISTENCE_ID}",
        )
        metadata = Metadata.model_validate_json(metadata_raw)
        assert metadata.original_eicr_id == EXPECTED_ORIGINAL_EICR_ID
        assert metadata.augmented_eicr_id == EXPECTED_ORIGINAL_EICR_ID
        assert metadata.original_eicr_id.root != TEST_PERSISTENCE_ID
        assert metadata.original_eicr_id.extension != TEST_PERSISTENCE_ID
        assert metadata.augmented_eicr_id.root != TEST_PERSISTENCE_ID
        assert metadata.augmented_eicr_id.extension != TEST_PERSISTENCE_ID
        assert metadata.error == "augmentation boom"
        assert metadata.passthrough_reason == PassthroughReason.AUGMENTATION_EXCEPTION
        snapshot.assert_match(
            _serialize_snapshot_value(metadata.model_dump(mode="json")),
            "augmentation_fails.json",
        )

    def test_build_augmentation_output_uses_null_flavor_when_passthrough_reason_is_present_without_original_eicr_id(
        self, mocker
    ) -> None:
        augmenter_mock = mocker.patch("augmentation_lambda.lambda_function.EICRAugmenter")

        output = lambda_function._build_augmentation_output(
            persistence_id=TEST_PERSISTENCE_ID,
            original_eicr="<ClinicalDocument />",
            augmenter_input=TTCAugmenterInput(
                persistence_id=TEST_PERSISTENCE_ID,
                original_eicr_id=None,
                passthrough_reason=PassthroughReason.NO_RELEVANT_SCHEMATRON_ERRORS,
            ),
        )

        augmenter_mock.assert_not_called()
        assert output.persistence_id == TEST_PERSISTENCE_ID
        assert output.augmented_eicr == "<ClinicalDocument />"
        assert output.metadata.original_eicr_id == CdaInstanceIdentifier(null_flavor="NI")
        assert output.metadata.augmented_eicr_id == CdaInstanceIdentifier(null_flavor="NI")
        assert output.metadata.passthrough_reason == PassthroughReason.NO_RELEVANT_SCHEMATRON_ERRORS

    def test_build_augmentation_output_raises_when_augmenter_constructor_fails_without_original_eicr_id(
        self, mocker
    ) -> None:
        augmenter_mock = mocker.patch(
            "augmentation_lambda.lambda_function.EICRAugmenter",
            side_effect=RuntimeError("constructor boom"),
        )

        with pytest.raises(RuntimeError, match="constructor boom"):
            lambda_function._build_augmentation_output(
                persistence_id=TEST_PERSISTENCE_ID,
                original_eicr="<ClinicalDocument />",
                augmenter_input=TTCAugmenterInput(
                    persistence_id=TEST_PERSISTENCE_ID,
                    original_eicr_id=None,
                    passthrough_reason=None,
                ),
            )

        augmenter_mock.assert_called_once()

    def test_handler_writes_original_eicr_when_augmented_eicr_validation_throws(
        self,
        example_sqs_event,
        mock_aws_setup,
        mocker,
        mock_lambda_context,
    ) -> None:
        original_eicr = lambda_handler.get_file_content_from_s3(
            bucket_name=S3_BUCKET,
            object_key=f"TextToCodeSubmissionV2/{TEST_PERSISTENCE_ID}",
        )

        validate_mock = mocker.patch(
            "augmentation_lambda.lambda_function.validate_eicr",
            side_effect=RuntimeError("validation boom"),
        )

        result = lambda_function.handler(example_sqs_event, mock_lambda_context)

        assert result["statusCode"] == SUCCESS_CODE
        assert result["message"] == "Augmentation processed successfully!"
        assert result["num_success_eicrs"] == 1
        validate_mock.assert_called_once()

        augmented_eicr = lambda_handler.get_file_content_from_s3(
            bucket_name=S3_BUCKET,
            object_key=f"{AUGMENTED_EICR_PREFIX}{TEST_PERSISTENCE_ID}",
        )
        assert augmented_eicr == original_eicr

        metadata_raw = lambda_handler.get_file_content_from_s3(
            bucket_name=S3_BUCKET,
            object_key=f"{AUGMENTATION_METADATA_PREFIX}{TEST_PERSISTENCE_ID}",
        )
        metadata = Metadata.model_validate_json(metadata_raw)

        assert metadata.original_eicr_id == EXPECTED_ORIGINAL_EICR_ID
        assert metadata.augmented_eicr_id == EXPECTED_ORIGINAL_EICR_ID
        assert metadata.error == "validation boom"
        assert metadata.passthrough_reason == PassthroughReason.AUGMENTATION_VALIDATION_FAILURE

    def test_handler_writes_original_eicr_when_augmentation_introduces_new_validation_error(
        self,
        example_sqs_event,
        mock_aws_setup,
        mocker,
        mock_lambda_context,
    ) -> None:
        original_eicr = lambda_handler.get_file_content_from_s3(
            bucket_name=S3_BUCKET,
            object_key=f"TextToCodeSubmissionV2/{TEST_PERSISTENCE_ID}",
        )
        # A pre-existing result-value finding the augmenter does not own, and a new error
        # only present after augmentation. Only the new one should block the output.
        preexisting_error = ValidationResult(
            error_id="ttc-labResultValue-PQNoInterp",
            location="/ClinicalDocument[1]/component[1]/structuredBody[1]/component[6]",
        )
        new_error = ValidationResult(
            error_id="ttc-labTestNameResulted-wrongCode",
            location="/ClinicalDocument[1]/component[1]/structuredBody[1]/component[7]",
        )

        validate_mock = mocker.patch(
            "augmentation_lambda.lambda_function.validate_eicr",
            # First call validates the augmented eICR, second the original (baseline).
            side_effect=[[new_error, preexisting_error], [preexisting_error]],
        )

        result = lambda_function.handler(example_sqs_event, mock_lambda_context)

        assert result["statusCode"] == SUCCESS_CODE
        assert result["message"] == "Augmentation processed successfully!"
        assert result["num_success_eicrs"] == 1
        assert validate_mock.call_count == EXPECTED_DIFF_VALIDATION_CALLS

        augmented_eicr = lambda_handler.get_file_content_from_s3(
            bucket_name=S3_BUCKET,
            object_key=f"{AUGMENTED_EICR_PREFIX}{TEST_PERSISTENCE_ID}",
        )
        assert augmented_eicr == original_eicr

        metadata_raw = lambda_handler.get_file_content_from_s3(
            bucket_name=S3_BUCKET,
            object_key=f"{AUGMENTATION_METADATA_PREFIX}{TEST_PERSISTENCE_ID}",
        )
        metadata = Metadata.model_validate_json(metadata_raw)

        assert metadata.original_eicr_id == EXPECTED_ORIGINAL_EICR_ID
        assert metadata.augmented_eicr_id == EXPECTED_ORIGINAL_EICR_ID
        # Only the newly-introduced error is recorded, not the pre-existing one.
        assert metadata.error == json.dumps([new_error.model_dump()])
        assert metadata.passthrough_reason == PassthroughReason.AUGMENTATION_VALIDATION_FAILURE

    def test_handler_emits_augmented_eicr_when_validation_errors_are_preexisting(
        self,
        example_sqs_event,
        mock_aws_setup,
        mocker,
        mock_lambda_context,
    ) -> None:
        original_eicr = lambda_handler.get_file_content_from_s3(
            bucket_name=S3_BUCKET,
            object_key=f"TextToCodeSubmissionV2/{TEST_PERSISTENCE_ID}",
        )
        # The same finding is present before and after augmentation: augmentation did not
        # introduce it, so the augmented eICR must still be emitted (no passthrough).
        preexisting_error = ValidationResult(
            error_id="ttc-labResultValue-PQNoInterp",
            location="/ClinicalDocument[1]/component[1]/structuredBody[1]/component[6]",
        )

        validate_mock = mocker.patch(
            "augmentation_lambda.lambda_function.validate_eicr",
            side_effect=[[preexisting_error], [preexisting_error]],
        )

        result = lambda_function.handler(example_sqs_event, mock_lambda_context)

        assert result["statusCode"] == SUCCESS_CODE
        assert result["message"] == "Augmentation processed successfully!"
        assert result["num_success_eicrs"] == 1
        assert validate_mock.call_count == EXPECTED_DIFF_VALIDATION_CALLS

        augmented_eicr = lambda_handler.get_file_content_from_s3(
            bucket_name=S3_BUCKET,
            object_key=f"{AUGMENTED_EICR_PREFIX}{TEST_PERSISTENCE_ID}",
        )
        assert augmented_eicr != original_eicr

        metadata_raw = lambda_handler.get_file_content_from_s3(
            bucket_name=S3_BUCKET,
            object_key=f"{AUGMENTATION_METADATA_PREFIX}{TEST_PERSISTENCE_ID}",
        )
        metadata = Metadata.model_validate_json(metadata_raw)

        assert metadata.augmented_eicr_id == EXPECTED_AUGMENTED_EICR_ID
        assert metadata.error is None
        assert metadata.passthrough_reason is None

    def test_build_augmentation_output_uses_root_and_extension_when_passthrough_reason_is_present(
        self, mocker
    ) -> None:
        augmenter_mock = mocker.patch("augmentation_lambda.lambda_function.EICRAugmenter")
        output = lambda_function._build_augmentation_output(
            persistence_id=TEST_PERSISTENCE_ID,
            original_eicr="<ClinicalDocument />",
            augmenter_input=TTCAugmenterInput(
                persistence_id=TEST_PERSISTENCE_ID,
                original_eicr_id=CdaInstanceIdentifier(
                    root=EXPECTED_ORIGINAL_EICR_ID.root,
                    extension="extension-1",
                ),
                passthrough_reason=PassthroughReason.NO_CODE_MATCHES,
            ),
        )

        augmenter_mock.assert_not_called()
        assert output.persistence_id == TEST_PERSISTENCE_ID
        assert output.augmented_eicr == "<ClinicalDocument />"
        assert output.metadata.original_eicr_id == CdaInstanceIdentifier(
            root=EXPECTED_ORIGINAL_EICR_ID.root,
            extension="extension-1",
        )
        assert output.metadata.augmented_eicr_id == CdaInstanceIdentifier(
            root=EXPECTED_ORIGINAL_EICR_ID.root,
            extension="extension-1",
        )
        assert output.metadata.passthrough_reason == PassthroughReason.NO_CODE_MATCHES

    def test_build_augmentation_output_uses_extension_when_passthrough_reason_is_present(
        self, mocker
    ) -> None:
        augmenter_mock = mocker.patch("augmentation_lambda.lambda_function.EICRAugmenter")
        output = lambda_function._build_augmentation_output(
            persistence_id=TEST_PERSISTENCE_ID,
            original_eicr="<ClinicalDocument />",
            augmenter_input=TTCAugmenterInput(
                persistence_id=TEST_PERSISTENCE_ID,
                original_eicr_id=CdaInstanceIdentifier(extension="extension-only"),
                passthrough_reason=PassthroughReason.NO_CODE_MATCHES,
            ),
        )

        augmenter_mock.assert_not_called()
        assert output.persistence_id == TEST_PERSISTENCE_ID
        assert output.augmented_eicr == "<ClinicalDocument />"
        assert output.metadata.original_eicr_id == CdaInstanceIdentifier(extension="extension-only")
        assert output.metadata.augmented_eicr_id == CdaInstanceIdentifier(
            extension="extension-only"
        )
        assert output.metadata.passthrough_reason == PassthroughReason.NO_CODE_MATCHES

    def test_build_original_eicr_output_sets_metadata_ids_to_original_eicr_id(self) -> None:
        output = lambda_function._build_original_eicr_output(
            persistence_id=TEST_PERSISTENCE_ID,
            original_eicr_id=EXPECTED_ORIGINAL_EICR_ID,
            original_eicr="<ClinicalDocument />",
            nonstandard_codes=[],
            passthrough_reason=PassthroughReason.NO_CODE_MATCHES,
        )

        assert output.persistence_id == TEST_PERSISTENCE_ID
        assert output.augmented_eicr == "<ClinicalDocument />"
        assert output.metadata.original_eicr_id == EXPECTED_ORIGINAL_EICR_ID
        assert output.metadata.augmented_eicr_id == EXPECTED_ORIGINAL_EICR_ID
        assert output.metadata.nonstandard_codes == []
        assert output.metadata.error is None
        assert output.metadata.passthrough_reason == PassthroughReason.NO_CODE_MATCHES

    def test_handler_source_bucket_routing(
        self,
        example_s3_event_payload,
        mock_aws_setup,
        snapshot: Snapshot,
        mock_lambda_context,
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
            result = lambda_function.handler(event, mock_lambda_context)
        snapshot.assert_match(
            _serialize_snapshot_value(result),
            "handler_source_bucket_routing_result.json",
        )

        augmented_eicr = lambda_handler.get_file_content_from_s3(
            bucket_name=custom_bucket,
            object_key=f"{AUGMENTED_EICR_PREFIX}{TEST_PERSISTENCE_ID}",
        )
        snapshot.assert_match(
            augmented_eicr,
            "handler_source_bucket_routing_augmented_eicr.xml",
        )

        # Validate augmented eICR
        actual_validation_results = validate_eicr(augmented_eicr)
        assert actual_validation_results == []  # Empty list means no errors.

    def test_handler_error_missing_eicr(
        self, example_s3_event_payload, mock_aws_setup, snapshot: Snapshot, mock_lambda_context
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

        result = lambda_function.handler(event, mock_lambda_context)

        assert result["num_failure_eicrs"] == 1
        assert len(result["failures"]) == 1
        snapshot.assert_match(
            _serialize_snapshot_value(result),
            "handler_error_missing_eicr_result.json",
        )

    def test_handler_error_missing_ttc_output(
        self, example_s3_event_payload, mock_aws_setup, snapshot: Snapshot, mock_lambda_context
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

        result = lambda_function.handler(event, mock_lambda_context)

        assert result["num_failure_eicrs"] == 1
        assert len(result["failures"]) == 1
        snapshot.assert_match(
            _serialize_snapshot_value(result),
            "handler_error_missing_ttc_output_result.json",
        )

    def test_handler_mixed_batch_results(
        self, example_s3_event_payload, mock_aws_setup, snapshot: Snapshot, mock_lambda_context
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

        result = lambda_function.handler(event, mock_lambda_context)

        assert result["num_success_eicrs"] == 1
        assert result["num_failure_eicrs"] == 1
        snapshot.assert_match(
            _serialize_snapshot_value(result),
            "handler_mixed_batch_results_result.json",
        )

    def test_handler_skips_empty_sqs_body(self, mock_aws_setup, mock_lambda_context) -> None:
        event = _build_empty_body_event()

        result = lambda_function.handler(event, mock_lambda_context)

        assert result["statusCode"] == SUCCESS_CODE
        assert result["message"] == "Augmentation processed successfully!"
        assert result["num_success_eicrs"] == 1
