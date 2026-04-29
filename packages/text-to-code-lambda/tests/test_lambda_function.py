import json

import pytest
from pytest_snapshot.plugin import Snapshot

import lambda_handler
from conftest import S3_BUCKET
from conftest import TTC_METADATA_PREFIX
from conftest import TTC_OUTPUT_PREFIX
from text_to_code_lambda import lambda_function

EXPECTED_RESULTED_ERRORS = 2
EXPECTED_ORDERED_ERRORS = 2
EXPECTED_EXCEPTION_RESULTS = 2


def _serialize_ttc_output_snapshot(ttc_output: dict[str, object]) -> str:
    normalized = json.loads(json.dumps(ttc_output))
    normalized["persistence_id"] = "<persistence_id>"
    return json.dumps(normalized, indent=2, sort_keys=True)


def _serialize_ttc_metadata_snapshot(ttc_metadata_output: dict[str, object]) -> str:
    normalized = json.loads(json.dumps(ttc_metadata_output))
    normalized["persistence_id"] = "<persistence_id>"
    normalized["processed_at"] = "<processed_at>"

    for field_errors in normalized.get("schematron_errors", {}).values():
        for error in field_errors:
            if (
                "opensearch_retrieved_scores" in error
                and error["opensearch_retrieved_scores"] is not None
            ):
                error["opensearch_retrieved_scores"] = "<opensearch_retrieved_scores>"

            if (
                "reranker_processed_results" in error
                and error["reranker_processed_results"] is not None
            ):
                for result in error["reranker_processed_results"]:
                    if "score" in result and result["score"] is not None:
                        result["score"] = f"{float(result['score']):.3f}"

    return json.dumps(normalized, indent=2, sort_keys=True)


class MockLambdaContext:
    function_name = "ttc-lambda"
    memory_limit_in_mb = 128
    invoked_function_arn = "arn:aws:lambda:us-east-1:123456789012:function:ttc-lambda"
    aws_request_id = "test-request-id"


class TestHandler:
    def test_handler_success(
        self,
        example_sqs_event,
        mock_aws_setup,
        mock_opensearch,
        mocker,
        snapshot: Snapshot,
    ):
        """Test handler with no failures."""
        selected_candidate = {
            "value": "weed allergen mix 3",
            "confidence": 1.0,
        }

        mocker.patch(
            "text_to_code.services.evaluator.select_relevant_text",
            return_value=type("SelectedCandidate", (), selected_candidate)(),
        )

        resp = lambda_function.handler(example_sqs_event, MockLambdaContext())
        assert resp == {
            "statusCode": 200,
            "message": "TTC processed successfully!",
            "num_success_eicrs": 1,
        }

        # Assert that the TTC output was saved to S3
        ttc_output = json.loads(
            lambda_handler.get_file_content_from_s3(
                bucket_name=S3_BUCKET,
                object_key=f"{TTC_OUTPUT_PREFIX}{mock_aws_setup.persistence_id}",
            )
        )
        assert ttc_output is not None
        snapshot.assert_match(
            _serialize_ttc_output_snapshot(ttc_output),
            "handler_success_ttc_output.json",
        )

        ttc_metadata_output = json.loads(
            lambda_handler.get_file_content_from_s3(
                bucket_name=S3_BUCKET,
                object_key=f"{TTC_METADATA_PREFIX}{mock_aws_setup.persistence_id.removesuffix('.xml')}.json",
            )
        )
        assert ttc_metadata_output is not None
        snapshot.assert_match(
            _serialize_ttc_metadata_snapshot(ttc_metadata_output),
            "handler_success_ttc_metadata_output.json",
        )

    def test_handler_with_no_records(self, example_sqs_event, mock_opensearch):
        """Test handler with no records."""
        example_sqs_event["Records"] = []
        expected_num_errors = 0
        resp = lambda_function.handler(example_sqs_event, MockLambdaContext())
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
        resp = lambda_function.handler(example_sqs_event, MockLambdaContext())
        assert "Empty SQS body" in caplog_warning.text
        assert resp == {
            "statusCode": 200,
            "message": "TTC processed successfully!",
            "num_success_eicrs": 1,
        }
        assert mock_opensearch.search.call_count == expected_num_errors

    def test_handler_fails_when_event_has_no_bucket(self, example_sqs_event, mock_opensearch):
        """Test handler reports failure when S3 event payload is missing a bucket name."""
        payload = json.loads(example_sqs_event["Records"][0]["body"])
        del payload["detail"]["bucket"]["name"]
        example_sqs_event["Records"][0]["body"] = json.dumps(payload)

        resp = lambda_function.handler(example_sqs_event, MockLambdaContext())

        assert resp["num_failure_eicrs"] == 1
        assert resp["num_success_eicrs"] == 0
        assert "No bucket name found" in resp["failures"][0]["error"]

    def test_handler_saves_metadata_when_no_relevant_schematron_fields(
        self, example_sqs_event, mock_aws_setup, mock_opensearch, mocker, snapshot: Snapshot
    ):
        """Test handler saves TTC metadata output when no relevant Schematron fields are found."""
        mocker.patch(
            "text_to_code_lambda.lambda_function._load_schematron_data_fields", return_value=[]
        )

        resp = lambda_function.handler(example_sqs_event, MockLambdaContext())
        assert resp == {
            "statusCode": 200,
            "message": "TTC processed successfully!",
            "num_success_eicrs": 1,
        }

        # Assert that the TTC output was not saved to S3
        with pytest.raises(FileNotFoundError):
            lambda_handler.get_file_content_from_s3(
                bucket_name=S3_BUCKET,
                object_key=f"{TTC_OUTPUT_PREFIX}{mock_aws_setup.persistence_id}",
            )

        # Assert that the TTC metadata output was saved to S3 with the expected content
        ttc_metadata_output = json.loads(
            lambda_handler.get_file_content_from_s3(
                bucket_name=S3_BUCKET,
                object_key=f"{TTC_METADATA_PREFIX}{mock_aws_setup.persistence_id.removesuffix('.xml')}.json",
            )
        )
        assert ttc_metadata_output is not None
        snapshot.assert_match(
            _serialize_ttc_metadata_snapshot(ttc_metadata_output),
            "handler_no_relevant_schematron_fields_ttc_metadata_output.json",
        )
        assert mock_opensearch.search.call_count == 0

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

        resp = lambda_function.handler(example_sqs_event, MockLambdaContext())

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

        resp = lambda_function.handler(example_sqs_event, MockLambdaContext())

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

    def test_handler_continues_when_selected_candidate_is_none(
        self, example_sqs_event, mock_aws_setup, mock_opensearch, mocker, snapshot: Snapshot
    ):
        """Test handler skips embedding and OpenSearch when no candidate is selected."""
        mocker.patch(
            "text_to_code.services.evaluator.select_relevant_text",
            return_value=None,
        )

        retriever_embed_mock = mocker.patch.object(lambda_function, "embed")
        reranker_mock = mocker.patch.object(lambda_function, "rerank")

        resp = lambda_function.handler(example_sqs_event, MockLambdaContext())

        assert resp == {
            "statusCode": 200,
            "message": "TTC processed successfully!",
            "num_success_eicrs": 1,
        }

        retriever_embed_mock.assert_not_called()
        reranker_mock.assert_not_called()
        assert mock_opensearch.search.call_count == 0

        ttc_output = json.loads(
            lambda_handler.get_file_content_from_s3(
                bucket_name=S3_BUCKET,
                object_key=f"{TTC_OUTPUT_PREFIX}{mock_aws_setup.persistence_id}",
            )
        )
        assert ttc_output is not None
        snapshot.assert_match(
            _serialize_ttc_output_snapshot(ttc_output),
            "handler_selected_candidate_none_ttc_output.json",
        )

        ttc_metadata_output = json.loads(
            lambda_handler.get_file_content_from_s3(
                bucket_name=S3_BUCKET,
                object_key=f"{TTC_METADATA_PREFIX}{mock_aws_setup.persistence_id.removesuffix('.xml')}.json",
            )
        )
        assert ttc_metadata_output is not None
        snapshot.assert_match(
            _serialize_ttc_metadata_snapshot(ttc_metadata_output),
            "handler_selected_candidate_none_ttc_metadata_output.json",
        )

    def test_handler_adds_unmatched_error_when_selected_candidate_has_no_opensearch_hits(
        self, example_sqs_event, mock_aws_setup, mock_opensearch, mocker, snapshot: Snapshot
    ):
        """Test handler records unmatched errors when a selected candidate has no OpenSearch hits."""
        selected_candidate = {
            "value": "weed allergen mix 3",
            "confidence": 1.0,
        }

        mocker.patch(
            "text_to_code.services.evaluator.select_relevant_text",
            return_value=type("SelectedCandidate", (), selected_candidate)(),
        )

        empty_opensearch_scores = type(
            "OpenSearchScores",
            (),
            {"hits": type("Hits", (), {"hits": []})()},
        )()

        mocker.patch(
            "text_to_code_lambda.lambda_function.lambda_handler.retrieve_opensearch_results",
            return_value=empty_opensearch_scores,
        )

        reranker_mock = mocker.patch.object(
            lambda_function,
            "rerank",
            return_value=[],
        )

        resp = lambda_function.handler(example_sqs_event, MockLambdaContext())

        assert resp == {
            "statusCode": 200,
            "message": "TTC processed successfully!",
            "num_success_eicrs": 1,
        }

        assert mock_opensearch.search.call_count == 0
        assert reranker_mock.call_count == EXPECTED_RESULTED_ERRORS + EXPECTED_ORDERED_ERRORS

        ttc_output = json.loads(
            lambda_handler.get_file_content_from_s3(
                bucket_name=S3_BUCKET,
                object_key=f"{TTC_OUTPUT_PREFIX}{mock_aws_setup.persistence_id}",
            )
        )
        assert ttc_output is not None
        snapshot.assert_match(
            _serialize_ttc_output_snapshot(ttc_output),
            "handler_no_opensearch_hits_ttc_output.json",
        )

        ttc_metadata_output = json.loads(
            lambda_handler.get_file_content_from_s3(
                bucket_name=S3_BUCKET,
                object_key=f"{TTC_METADATA_PREFIX}{mock_aws_setup.persistence_id.removesuffix('.xml')}.json",
            )
        )
        assert ttc_metadata_output is not None
        snapshot.assert_match(
            _serialize_ttc_metadata_snapshot(ttc_metadata_output),
            "handler_no_opensearch_hits_ttc_metadata_output.json",
        )

    def test_process_record_pipeline_returns_no_matches_found_when_no_candidates_are_selected(
        self, mock_aws_setup, mock_opensearch, mocker
    ):
        """Test pipeline returns no_matches_found when no relevant candidates are selected."""
        mocker.patch(
            "text_to_code.services.evaluator.select_relevant_text",
            return_value=None,
        )

        s3_client = lambda_handler.create_s3_client()

        resp = lambda_function._process_record_pipeline(
            persistence_id=mock_aws_setup.persistence_id,
            s3_client=s3_client,
            opensearch_client=mock_opensearch,
            bucket_name=S3_BUCKET,
        )

        assert resp == {
            "statusCode": 200,
            "message": "TTC processed successfully, but no relevant candidates or code matches were found.",
            "result": "no_matches_found",
        }
