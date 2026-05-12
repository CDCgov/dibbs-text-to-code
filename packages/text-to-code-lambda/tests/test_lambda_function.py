import json
from datetime import UTC
from datetime import datetime

import pytest
from pytest_snapshot.plugin import Snapshot

import lambda_handler
from conftest import S3_BUCKET
from conftest import TTC_METADATA_PREFIX
from conftest import TTC_OUTPUT_PREFIX
from text_to_code_lambda import lambda_function
from text_to_code_lambda.lambda_function import Failure
from text_to_code_lambda.lambda_function import FailureResponse
from text_to_code_lambda.lambda_function import SuccessResponse

EXPECTED_RESULTED_ERRORS = 2
EXPECTED_ORDERED_ERRORS = 2
EXPECTED_EXCEPTION_RESULTS = 2


@pytest.mark.time_machine(datetime(2026, 1, 1, 1, 1, 0, 0, tzinfo=UTC), tick=False)
class TestHandler:
    def test_handler_success(
        self,
        example_sqs_event,
        mock_aws_setup,
        mock_opensearch,
        snapshot: Snapshot,
        mock_lambda_context,
    ):
        """Test handler with no failures."""
        resp = lambda_function.handler(example_sqs_event, mock_lambda_context)
        assert resp == SuccessResponse(num_success_eicrs=1)
        # Assert that the TTC output was saved to S3
        ttc_output = json.dumps(
            json.loads(
                lambda_handler.get_file_content_from_s3(
                    bucket_name=S3_BUCKET,
                    object_key=f"{TTC_OUTPUT_PREFIX}{mock_aws_setup.persistence_id}",
                )
            ),
            indent=4,
            sort_keys=True,
        )
        snapshot.assert_match(ttc_output, "handler_success_ttc_output.json")

        ttc_metadata_output = json.dumps(
            json.loads(
                lambda_handler.get_file_content_from_s3(
                    bucket_name=S3_BUCKET,
                    object_key=f"{TTC_METADATA_PREFIX}{mock_aws_setup.persistence_id.removesuffix('.xml')}.json",
                )
            ),
            indent=4,
            sort_keys=True,
        )
        assert ttc_metadata_output is not None
        snapshot.assert_match(ttc_metadata_output, "handler_success_ttc_metadata_output.json")

    def test_handler_with_no_records(self, example_sqs_event, mock_opensearch, mock_lambda_context):
        """Test handler with no records."""
        example_sqs_event["Records"] = []
        resp = lambda_function.handler(example_sqs_event, mock_lambda_context)
        assert resp == SuccessResponse(num_success_eicrs=0)

        assert mock_opensearch.search.call_count == 0

    def test_handler_with_empty_body(
        self, example_sqs_event, caplog_warning, mock_opensearch, mock_lambda_context
    ):
        """Test handler with an empty SQS body."""
        example_sqs_event["Records"][0]["body"] = None
        expected_num_errors = 0
        resp = lambda_function.handler(example_sqs_event, mock_lambda_context)
        assert "Empty SQS body" in caplog_warning.text
        assert resp == SuccessResponse(num_success_eicrs=0)
        assert mock_opensearch.search.call_count == expected_num_errors

    def test_handler_fails_when_event_has_no_bucket(
        self, example_sqs_event, mock_opensearch, mock_lambda_context
    ):
        """Test handler reports failure when S3 event payload is missing a bucket name."""
        payload = json.loads(example_sqs_event["Records"][0]["body"])
        del payload["detail"]["bucket"]["name"]
        example_sqs_event["Records"][0]["body"] = json.dumps(payload)

        resp = lambda_function.handler(example_sqs_event, mock_lambda_context)

        assert resp == FailureResponse(
            num_success_eicrs=0,
            num_failure_eicrs=1,
            failures=[
                Failure(
                    error="No bucket name found in S3 event payload. The TTC lambda derives its target bucket from the event and does not use a static bucket configuration. Ensure the EventBridge/S3 event includes detail.bucket.name.",
                    message_id="f9ccdff5-0acb-4933-8995-bd7f0ab5f2f7",
                )
            ],
        )

    def test_handler_saves_metadata_when_no_relevant_schematron_fields(
        self,
        example_sqs_event,
        mock_aws_setup_no_schematron_issues,
        mock_opensearch,
        snapshot: Snapshot,
        mock_lambda_context,
    ):
        """Test handler saves TTC metadata output when no relevant Schematron fields are found."""
        resp = lambda_function.handler(example_sqs_event, mock_lambda_context)
        assert resp == SuccessResponse(num_success_eicrs=0)

        # Assert that the TTC output was not saved to S3
        with pytest.raises(FileNotFoundError):
            lambda_handler.get_file_content_from_s3(
                bucket_name=S3_BUCKET,
                object_key=f"{TTC_OUTPUT_PREFIX}{mock_aws_setup_no_schematron_issues.persistence_id}",
            )

        # Assert that the TTC metadata output was saved to S3 with the expected content
        ttc_metadata_output = json.dumps(
            json.loads(
                lambda_handler.get_file_content_from_s3(
                    bucket_name=S3_BUCKET,
                    object_key=f"{TTC_METADATA_PREFIX}{mock_aws_setup_no_schematron_issues.persistence_id.removesuffix('.xml')}.json",
                )
            ),
            indent=4,
            sort_keys=True,
        )
        snapshot.assert_match(
            ttc_metadata_output, "handler_no_relevant_schematron_fields_ttc_metadata_output.json"
        )

    def test_handler_continues_when_selected_candidate_is_none(
        self,
        example_sqs_event,
        mock_aws_setup,
        mock_opensearch,
        mocker,
        snapshot: Snapshot,
        mock_lambda_context,
    ):
        """Test handler skips embedding and OpenSearch when no candidate is selected."""
        mocker.patch(
            "text_to_code.services.evaluator.select_relevant_text",
            return_value=None,
        )

        retriever_embed_mock = mocker.patch.object(lambda_function, "embed")
        reranker_mock = mocker.patch.object(lambda_function, "rerank")

        resp = lambda_function.handler(example_sqs_event, mock_lambda_context)

        assert resp == SuccessResponse(num_success_eicrs=1)

        retriever_embed_mock.assert_not_called()
        reranker_mock.assert_not_called()
        assert mock_opensearch.search.call_count == 0

        ttc_output = json.dumps(
            json.loads(
                lambda_handler.get_file_content_from_s3(
                    bucket_name=S3_BUCKET,
                    object_key=f"{TTC_OUTPUT_PREFIX}{mock_aws_setup.persistence_id}",
                )
            ),
            indent=4,
            sort_keys=True,
        )
        snapshot.assert_match(ttc_output, "handler_success_ttc_output.json")

        snapshot.assert_match(
            ttc_output,
            "handler_selected_candidate_none_ttc_output.json",
        )

        ttc_metadata_output = json.dumps(
            json.loads(
                lambda_handler.get_file_content_from_s3(
                    bucket_name=S3_BUCKET,
                    object_key=f"{TTC_METADATA_PREFIX}{mock_aws_setup.persistence_id.removesuffix('.xml')}.json",
                )
            ),
            indent=4,
            sort_keys=True,
        )
        snapshot.assert_match(
            ttc_metadata_output,
            "handler_selected_candidate_none_ttc_metadata_output.json",
        )

    def test_handler_adds_unmatched_error_when_selected_candidate_has_no_opensearch_hits(
        self,
        example_sqs_event,
        mock_aws_setup,
        mock_opensearch,
        mocker,
        snapshot: Snapshot,
        mock_lambda_context,
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

        resp = lambda_function.handler(example_sqs_event, mock_lambda_context)

        assert resp == SuccessResponse(num_success_eicrs=1)

        assert reranker_mock.call_count == 0

        ttc_output = json.dumps(
            json.loads(
                lambda_handler.get_file_content_from_s3(
                    bucket_name=S3_BUCKET,
                    object_key=f"{TTC_OUTPUT_PREFIX}{mock_aws_setup.persistence_id}",
                )
            ),
            indent=4,
            sort_keys=True,
        )
        snapshot.assert_match(
            ttc_output,
            "handler_no_opensearch_hits_ttc_output.json",
        )

        ttc_metadata_output = json.dumps(
            json.loads(
                lambda_handler.get_file_content_from_s3(
                    bucket_name=S3_BUCKET,
                    object_key=f"{TTC_METADATA_PREFIX}{mock_aws_setup.persistence_id.removesuffix('.xml')}.json",
                )
            ),
            indent=4,
            sort_keys=True,
        )
        snapshot.assert_match(
            ttc_metadata_output,
            "handler_no_opensearch_hits_ttc_metadata_output.json",
        )
