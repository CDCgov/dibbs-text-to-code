import json
from datetime import UTC
from datetime import datetime

import pytest
from pytest_snapshot.plugin import Snapshot

import lambda_handler
from text_to_code_lambda import lambda_function
from utils import get_env_var

S3_BUCKET = get_env_var("S3_BUCKET")
TTC_METADATA_PREFIX = get_env_var("TTC_METADATA_PREFIX")
TTC_OUTPUT_PREFIX = get_env_var("TTC_OUTPUT_PREFIX")

EXPECTED_ORDERED_ERRORS = 1
EXPECTED_EXCEPTION_RESULTS = 2
EXPECTED_RERANKER_SCORE = 0.944


@pytest.mark.time_machine(datetime(2026, 1, 1, 1, 1, 0, 0, tzinfo=UTC), tick=False)
class TestHandler:
    """Test the text to lambda handler.

    TODO: Comparing the output JSONs are problematic because they contain floating point numbers that can be different accross systems. Either the test needs to be updated to handle that, or the output models need to be update to handle comparisons.
    """

    def test_handler_success(
        self, example_sqs_event, mock_aws_setup, mock_opensearch, mocker, snapshot: Snapshot
    ):
        """Test handler with no failures."""
        resp = lambda_function.handler(example_sqs_event, {})
        assert resp == {
            "statusCode": 200,
            "message": "TTC processed successfully!",
            "num_success_eicrs": 1,
        }

        # Assert that the TTC output was saved to S3
        ttc_output = lambda_handler.get_file_content_from_s3(
            bucket_name=S3_BUCKET,
            object_key=f"{TTC_OUTPUT_PREFIX}{mock_aws_setup.persistence_id}",
        )
        snapshot.assert_match(ttc_output, "ttc_output.json")

        # Assert that the TTC metadata output was saved to S3 with the expected content
        ttc_metadata = lambda_handler.get_file_content_from_s3(
            bucket_name=S3_BUCKET,
            object_key=f"{TTC_METADATA_PREFIX}{mock_aws_setup.persistence_id}",
        )
        snapshot.assert_match(ttc_metadata, "ttc_metadata.json")

    def test_handler_with_no_records(self, example_sqs_event, mock_opensearch):
        """Test handler with no records."""
        example_sqs_event["Records"] = []
        expected_num_errors = 0
        resp = lambda_function.handler(example_sqs_event, {})
        assert resp == {
            "statusCode": 200,
            "message": "TTC processed successfully!",
            "num_success_eicrs": 0,
        }
        assert resp["num_success_eicrs"] == 0
        assert mock_opensearch.search.call_count == expected_num_errors

    def test_handler_with_empty_body(self, example_sqs_event, caplog_warning, mock_opensearch):
        """Test handler with an empty SQS body."""
        example_sqs_event["Records"][0]["body"] = None
        expected_num_errors = 0
        resp = lambda_function.handler(example_sqs_event, {})
        assert "Empty SQS body" in caplog_warning.text
        assert resp == {
            "statusCode": 200,
            "message": "TTC processed successfully!",
            "num_success_eicrs": 1,
        }
        assert mock_opensearch.search.call_count == expected_num_errors

    def test_handler_continues_processing_after_record_exception(
        self, example_sqs_event, mocker, mock_opensearch
    ):
        """Test handler continues processing remaining records when one record raises an exception."""
        example_sqs_event["Records"].append(json.loads(json.dumps(example_sqs_event["Records"][0])))
        example_sqs_event["Records"][1]["messageId"] = "second-message-id"

        process_record_mock = mocker.patch(
            "text_to_code_lambda.lambda_function.process_record",
            side_effect=[Exception("boom"), None],
        )

        resp = lambda_function.handler(example_sqs_event, {})

        assert process_record_mock.call_count == EXPECTED_EXCEPTION_RESULTS
        assert resp == {
            "statusCode": 200,
            "message": "TTC processed with some failures!",
            "failures": [
                {"message_id": example_sqs_event["Records"][0]["messageId"], "error": "boom"}
            ],
            "num_failure_eicrs": 1,
            "num_success_eicrs": 1,
        }
        assert mock_opensearch.search.call_count == 0

    def test_handler_returns_failures_when_all_records_raise(
        self, example_sqs_event, mocker, mock_opensearch
    ):
        """Test handler returns aggregated failures when all records raise exceptions."""
        example_sqs_event["Records"].append(json.loads(json.dumps(example_sqs_event["Records"][0])))
        example_sqs_event["Records"][0]["messageId"] = "first-message-id"
        example_sqs_event["Records"][1]["messageId"] = "second-message-id"

        process_record_mock = mocker.patch(
            "text_to_code_lambda.lambda_function.process_record",
            side_effect=[Exception("first failure"), Exception("second failure")],
        )

        resp = lambda_function.handler(example_sqs_event, {})

        assert process_record_mock.call_count == EXPECTED_EXCEPTION_RESULTS
        assert resp == {
            "statusCode": 200,
            "message": "TTC processed with some failures!",
            "failures": [
                {"message_id": "first-message-id", "error": "first failure"},
                {"message_id": "second-message-id", "error": "second failure"},
            ],
            "num_failure_eicrs": 2,
            "num_success_eicrs": 0,
        }
        assert mock_opensearch.search.call_count == 0

    def test_handler_saves_metadata_when_no_relevant_schematron_fields(
        self, example_sqs_event, mock_aws_setup_empty_eicr, mock_opensearch, mocker, snapshot
    ):
        """Test handler when there are no relevant Schematron fields."""
        resp = lambda_function.handler(example_sqs_event, {})
        assert resp == {
            "statusCode": 200,
            "message": "TTC processed successfully!",
            "num_success_eicrs": 1,
        }

        # Assert that the TTC output was saved to S3
        ttc_output = lambda_handler.get_file_content_from_s3(
            bucket_name=S3_BUCKET,
            object_key=f"{TTC_OUTPUT_PREFIX}{mock_aws_setup_empty_eicr.persistence_id}",
        )
        snapshot.assert_match(ttc_output, "ttc_output.json")

        # Assert that the TTC metadata output was saved to S3 with the expected content
        ttc_metadata = lambda_handler.get_file_content_from_s3(
            bucket_name=S3_BUCKET,
            object_key=f"{TTC_METADATA_PREFIX}{mock_aws_setup_empty_eicr.persistence_id}",
        )
        snapshot.assert_match(ttc_metadata, "ttc_metadata.json")
