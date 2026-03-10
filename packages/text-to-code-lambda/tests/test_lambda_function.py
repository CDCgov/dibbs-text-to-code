from text_to_code_lambda import lambda_function


class TestHandler:
    def test_handler_success(self, example_sqs_event, full_moto_setup, mock_opensearch):
        """Test handler with no failures."""
        expected_num_errors = 3
        resp = lambda_function.handler(example_sqs_event, {})
        assert resp == {
            "statusCode": 200,
            "message": "TTC processed successfully!",
            "num_successes": 1,
        }

        # Assert that the number of calls to opensearch_client.search is equal to the expected number of errors
        assert mock_opensearch.search.call_count == expected_num_errors

    def test_handler_with_no_records(self, example_sqs_event, mock_opensearch):
        """Test handler with no records."""
        example_sqs_event["Records"] = []
        expected_num_errors = 0
        resp = lambda_function.handler(example_sqs_event, {})
        assert resp == {
            "statusCode": 200,
            "message": "TTC processed successfully!",
            "num_successes": 0,
        }
        assert resp["num_successes"] == 0
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
            "num_successes": 1,
        }
        assert mock_opensearch.search.call_count == expected_num_errors

    # def test_handler_with_processing_failure(self, example_sqs_event, monkeypatch):
    #     """Test handler with a processing failure."""

    #     # Patch the process_record function to raise an exception for testing
    #     def mock_process_record(record) -> None:
    #         raise Exception("Test processing error")

    #     monkeypatch.setattr(lambda_function, "process_record", mock_process_record)

    #     resp = lambda_function.handler(example_sqs_event, {})
    #     assert resp["statusCode"] == 200
    #     assert resp["message"] == "TTC processed with some failures!"
    #     assert resp["num_failures"] == 1
    #     assert resp["num_successes"] == 0
    #     assert len(resp["failures"]) == 1
    #     assert resp["failures"][0]["error"] == "Test processing error"
