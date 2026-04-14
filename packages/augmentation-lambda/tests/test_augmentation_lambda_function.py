import json

import lambda_handler
from augmentation_lambda import lambda_function
from shared_models import DataField
from shared_models import NonstandardCodeInstance

S3_BUCKET = "dibbs-text-to-code"
TTC_OUTPUT_PREFIX = "TTCAugmentationMetadataV2/"
AUGMENTED_EICR_PREFIX = "AugmentationEICRV2/"
AUGMENTATION_METADATA_PREFIX = "AugmentationMetadataV2/"
TEST_PERSISTENCE_ID = "2025/09/03/1-5f84c7a5-91d7f5c6a2b7c9e08f0d1234"
SUCCESS_CODE = 200

TEST_TTC_OUTPUT = {
    "persistence_id": TEST_PERSISTENCE_ID,
    "eicr_metadata": {},
    "schematron_errors": {
        "Lab Test Name Resulted": [
            {
                "schematron_error": "Text to Code: Lab Test Name Resulted does not have a @code attribute",
                "schematron_error_xpath": "/ClinicalDocument/component/structuredBody/component/section/entry/component/observation",
                "field_type": "Lab Test Name Resulted",
                "new_translation": {
                    "code": "109224-6",
                    "code_system": "2.16.840.1.113883.6.1",
                    "code_system_name": "LOINC",
                    "display_name": "Weed Allergen Mix 3 IgE Ab",
                    "value_set": None,
                    "value_set_version": None,
                    "original_text": "A custom code in original text.",
                },
            }
        ]
    },
}


class TestParseNonstandardCodes:
    """Tests for the _parse_nonstandard_codes helper."""

    def test_parses_valid_ttc_output(self) -> None:
        codes = lambda_function._parse_nonstandard_codes(TEST_TTC_OUTPUT)

        assert len(codes) == 1
        assert isinstance(codes[0], NonstandardCodeInstance)
        assert codes[0].field_type == DataField.LAB_TEST_NAME_RESULTED
        assert codes[0].new_translation.code == "109224-6"
        assert codes[0].new_translation.code_system == "2.16.840.1.113883.6.1"
        assert codes[0].new_translation.display_name == "Weed Allergen Mix 3 IgE Ab"

    def test_skips_entries_without_new_translation(self) -> None:
        ttc_output = {
            "schematron_errors": {
                "Lab Test Name Resulted": [
                    {
                        "field": "Lab Test Name Resulted",
                        "error": "some error",
                        "error_context": "/some/xpath",
                    }
                ]
            }
        }

        codes = lambda_function._parse_nonstandard_codes(ttc_output)

        assert len(codes) == 0

    def test_handles_empty_schematron_errors(self) -> None:
        codes = lambda_function._parse_nonstandard_codes({"schematron_errors": {}})
        assert len(codes) == 0

    def test_handles_missing_schematron_errors(self) -> None:
        codes = lambda_function._parse_nonstandard_codes({})
        assert len(codes) == 0


class TestHandler:
    """Tests for the augmentation Lambda handler."""

    def test_handler_success(self, example_sqs_event, mock_aws_setup) -> None:
        result = lambda_function.handler(example_sqs_event, None)

        assert result["statusCode"] == SUCCESS_CODE
        assert result["message"] == "Augmentation processed successfully!"
        assert result["num_success_eicrs"] == 1

    def test_handler_writes_outputs_to_s3(self, example_sqs_event, mock_aws_setup) -> None:
        lambda_function.handler(example_sqs_event, None)

        # Verify augmented eICR was written
        augmented_eicr = lambda_handler.get_file_content_from_s3(
            bucket_name=S3_BUCKET,
            object_key=f"{AUGMENTED_EICR_PREFIX}{TEST_PERSISTENCE_ID}",
            s3_client=mock_aws_setup,
        )
        assert "ClinicalDocument" in augmented_eicr

        # Verify metadata was written
        metadata_raw = lambda_handler.get_file_content_from_s3(
            bucket_name=S3_BUCKET,
            object_key=f"{AUGMENTATION_METADATA_PREFIX}{TEST_PERSISTENCE_ID}",
            s3_client=mock_aws_setup,
        )
        metadata = json.loads(metadata_raw)
        assert "original_eicr_id" in metadata
        assert "augmented_eicr_id" in metadata

    def test_handler_source_bucket_routing(self, example_s3_event_payload, mock_aws_setup) -> None:
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
        event = {
            "Records": [
                {
                    "messageId": "msg-routing",
                    "receiptHandle": "test-receipt-handle",
                    "body": json.dumps(example_s3_event_payload),
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
            ]
        }

        lambda_function.handler(event, None)

        # Outputs should be in the custom bucket, not the default
        augmented_eicr = lambda_handler.get_file_content_from_s3(
            bucket_name=custom_bucket,
            object_key=f"{AUGMENTED_EICR_PREFIX}{TEST_PERSISTENCE_ID}",
            s3_client=mock_aws_setup,
        )
        assert "ClinicalDocument" in augmented_eicr

    def test_handler_error_missing_eicr(self, example_s3_event_payload, mock_aws_setup) -> None:
        """Test error when the original eICR is not found in S3."""
        # Remove the eICR from S3
        mock_aws_setup.delete_object(
            Bucket=S3_BUCKET,
            Key=f"TextToCodeSubmissionV2/{TEST_PERSISTENCE_ID}",
        )

        event = {
            "Records": [
                {
                    "messageId": "msg-missing-eicr",
                    "receiptHandle": "test-receipt-handle",
                    "body": json.dumps(example_s3_event_payload),
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
            ]
        }

        result = lambda_function.handler(event, None)

        assert result["num_failure_eicrs"] == 1
        assert len(result["failures"]) == 1

    def test_handler_error_missing_ttc_output(
        self, example_s3_event_payload, mock_aws_setup
    ) -> None:
        """Test error when the TTC output is not found in S3."""
        mock_aws_setup.delete_object(
            Bucket=S3_BUCKET,
            Key=f"{TTC_OUTPUT_PREFIX}{TEST_PERSISTENCE_ID}",
        )

        event = {
            "Records": [
                {
                    "messageId": "msg-missing-ttc",
                    "receiptHandle": "test-receipt-handle",
                    "body": json.dumps(example_s3_event_payload),
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
            ]
        }

        result = lambda_function.handler(event, None)

        assert result["num_failure_eicrs"] == 1
        assert len(result["failures"]) == 1

    def test_handler_mixed_batch_results(self, example_s3_event_payload, mock_aws_setup) -> None:
        """Test batch with both success and failure records."""
        # Create a second event pointing to a non-existent persistence ID
        bad_event_payload = example_s3_event_payload.copy()
        bad_event_payload = json.loads(json.dumps(example_s3_event_payload))
        bad_event_payload["detail"]["object"]["key"] = f"{TTC_OUTPUT_PREFIX}nonexistent/id"

        event = {
            "Records": [
                {
                    "messageId": "msg-success",
                    "receiptHandle": "test-receipt-handle",
                    "body": json.dumps(example_s3_event_payload),
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
                },
                {
                    "messageId": "msg-fail",
                    "receiptHandle": "test-receipt-handle-2",
                    "body": json.dumps(bad_event_payload),
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
                },
            ]
        }

        result = lambda_function.handler(event, None)

        assert result["num_success_eicrs"] == 1
        assert result["num_failure_eicrs"] == 1

    def test_handler_skips_empty_sqs_body(self, mock_aws_setup) -> None:
        event = {
            "Records": [
                {
                    "messageId": "msg-empty-body",
                    "receiptHandle": "test-receipt-handle",
                    "body": "",
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
            ]
        }

        result = lambda_function.handler(event, None)

        assert result["statusCode"] == SUCCESS_CODE
        assert result["message"] == "Augmentation processed successfully!"
        assert result["num_success_eicrs"] == 1
