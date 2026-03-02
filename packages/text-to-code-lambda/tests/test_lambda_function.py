from text_to_code_lambda import lambda_function


class TestHandler:

    def test_handler_success(self, example_sqs_event):
        """Test handler with no failures."""

        resp = lambda_function.handler(example_sqs_event, {})
        assert resp == {"statusCode": 200, "message": "TTC processed successfully!", "num_successes": 1}

    def test_handler_with_no_records(self, example_sqs_event):
        """Test handler with no records."""
        example_sqs_event["Records"] = []
        resp = lambda_function.handler(example_sqs_event, {})
        assert resp == {"statusCode": 200, "message": "TTC processed successfully!", "num_successes": 0}

    def test_handler_with_processing_failure(self, example_sqs_event, monkeypatch):
        """Test handler with a processing failure."""
        # Patch the process_record function to raise an exception for testing
        def mock_process_record(record):
            raise Exception("Test processing error")

        monkeypatch.setattr(lambda_function, "process_record", mock_process_record)

        resp = lambda_function.handler(example_sqs_event, {})
        assert resp["statusCode"] == 200
        assert resp["message"] == "TTC processed with some failures!"
        assert resp["num_failures"] == 1
        assert resp["num_successes"] == 0
        assert len(resp["failures"]) == 1
        assert resp["failures"][0]["error"] == "Test processing error"
