import json

import lambda_handler
from text_to_code_lambda import lambda_function

EXPECTED_RESULTED_ERRORS = 2
EXPECTED_ORDERED_ERRORS = 2


class TestHandler:
    def test_handler_success(self, example_sqs_event, mock_aws_setup, mock_opensearch):
        """Test handler with no failures."""
        expected_num_errors = 4
        resp = lambda_function.handler(example_sqs_event, {})
        assert resp == {
            "statusCode": 200,
            "message": "TTC processed successfully!",
            "num_success_eicrs": 1,
        }

        # Assert that the number of calls to opensearch_client.search is equal to the expected number of errors
        assert mock_opensearch.search.call_count == expected_num_errors

        # Assert that the TTC output was saved to S3
        ttc_output = json.loads(
            lambda_handler.get_file_content_from_s3(
                bucket_name=mock_aws_setup.ttc_output_bucket_name,
                object_key=mock_aws_setup.persistence_id,
            )
        )
        # TODO: update the content to match expected output type once we complete ticket #327 and update the test data
        assert ttc_output is not None
        assert ttc_output["persistence_id"] == mock_aws_setup.persistence_id
        assert "schematron_errors" in ttc_output
        assert "eicr_metadata" in ttc_output
        assert (
            len(ttc_output["schematron_errors"]["Lab Test Name Resulted"])
            == EXPECTED_RESULTED_ERRORS
        )
        assert (
            len(ttc_output["schematron_errors"]["Lab Test Name Ordered"]) == EXPECTED_ORDERED_ERRORS
        )
        assert (
            "opensearch_retrieved_scores"
            not in ttc_output["schematron_errors"]["Lab Test Name Resulted"][0]
        )
        assert "candidate" in ttc_output["schematron_errors"]["Lab Test Name Resulted"][0]
        assert "error_context" in ttc_output["schematron_errors"]["Lab Test Name Resulted"][0]
        assert "error_id" in ttc_output["schematron_errors"]["Lab Test Name Resulted"][0]

        # Assert that the TTC metadata output was saved to S3 with the expected content
        ttc_metadata_output = json.loads(
            lambda_handler.get_file_content_from_s3(
                bucket_name=mock_aws_setup.ttc_metadata_bucket_name,
                object_key=mock_aws_setup.persistence_id,
            )
        )
        assert ttc_metadata_output is not None
        assert ttc_metadata_output["persistence_id"] == mock_aws_setup.persistence_id
        assert "eicr_metadata" in ttc_metadata_output
        assert "schematron_errors" in ttc_metadata_output
        assert (
            len(ttc_metadata_output["schematron_errors"]["Lab Test Name Resulted"])
            == EXPECTED_RESULTED_ERRORS
        )
        assert (
            len(ttc_metadata_output["schematron_errors"]["Lab Test Name Ordered"])
            == EXPECTED_ORDERED_ERRORS
        )
        assert (
            "opensearch_retrieved_scores"
            in ttc_metadata_output["schematron_errors"]["Lab Test Name Resulted"][0]
        )

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
