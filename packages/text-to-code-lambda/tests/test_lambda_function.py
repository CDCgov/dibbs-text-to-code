import json
import os
from datetime import UTC, datetime

import pytest
from pytest_snapshot.plugin import Snapshot

import lambda_handler
from lambda_handler.models import OpenSearchHits, OpenSearchResult, OpenSearchShards
from text_to_code.models import Candidate, LabXPaths
from text_to_code.services.reranker import ScoredResult
from text_to_code_lambda import lambda_function

S3_BUCKET = os.environ["S3_BUCKET"]
TTC_OUTPUT_PREFIX = os.environ["TTC_OUTPUT_PREFIX"]
TTC_METADATA_PREFIX = os.environ["TTC_METADATA_PREFIX"]

EXPECTED_EXCEPTION_RESULTS = 2


def _get_serialized_object(key: str) -> str:
    return json.dumps(
        json.loads(
            lambda_handler.get_file_content_from_s3(
                bucket_name=S3_BUCKET,
                object_key=key,
            )
        ),
        indent=2,
        sort_keys=True,
    )


def _serialize_snapshot_value(value: dict[str, object]) -> str:
    normalized = json.loads(json.dumps(value))
    return json.dumps(normalized, indent=2, sort_keys=True)


@pytest.mark.time_machine(datetime(2026, 1, 1, 1, 1, 0, 0, tzinfo=UTC), tick=False)
class TestHandler:
    def test_handler_success(
        self,
        example_sqs_event,
        mock_aws_setup,
        mock_opensearch,
        snapshot: Snapshot,
        mock_lambda_context,
        mocker,
    ):
        """Test handler with no failures."""
        ranked_results: list[ScoredResult] = [
            {"code_string": "Weed Allerg Mix3 IgE Qn", "score": 0.7127664685249329},
            {
                "code_string": "(Artemisia vulgaris+Chenopodium album+Plantago lanceolata+Solidago virgaurea+Urtica dioica) Ab.IgE:PrThr:Pt:Ser:Ord:Multidisk",
                "score": 0.5247528553009033,
            },
            {
                "code_string": "Weed Allergen Mix 3 (Mugwort+Goosefoot or Lambs quarters+English plantain+Goldenrod+Nettle) IgE Ab [Measurement] in Serum",
                "score": 0.35545864701271057,
            },
        ]
        mocker.patch(
            "text_to_code_lambda.lambda_function.rerank",
            return_value=ranked_results,
        )

        resp = lambda_function.handler(example_sqs_event, mock_lambda_context)
        assert resp == {"batchItemFailures": []}

        ttc_output = _get_serialized_object(f"{TTC_OUTPUT_PREFIX}{mock_aws_setup.persistence_id}")
        snapshot.assert_match(ttc_output, "handler_success_ttc_output.json")

        ttc_metadata_output = _get_serialized_object(
            f"{TTC_METADATA_PREFIX}{mock_aws_setup.persistence_id.removesuffix('.xml')}.json"
        )
        snapshot.assert_match(ttc_metadata_output, "handler_success_ttc_metadata_output.json")

    def test_handler_with_no_records(self, example_sqs_event, mock_opensearch, mock_lambda_context):
        """Test handler with no records."""
        example_sqs_event["Records"] = []
        expected_num_errors = 0
        resp = lambda_function.handler(example_sqs_event, mock_lambda_context)
        assert resp == {"batchItemFailures": []}
        assert resp["batchItemFailures"] == []
        assert mock_opensearch.search.call_count == expected_num_errors

    def test_handler_with_empty_body(
        self, example_sqs_event, caplog_warning, mock_opensearch, mock_lambda_context
    ):
        """Test handler with an empty SQS body."""
        example_sqs_event["Records"][0]["body"] = None
        expected_num_errors = 0
        resp = lambda_function.handler(example_sqs_event, mock_lambda_context)
        assert "Empty SQS body" in caplog_warning.text
        assert resp == {"batchItemFailures": []}
        assert mock_opensearch.search.call_count == expected_num_errors

    def test_handler_fails_when_event_has_no_bucket(
        self,
        example_sqs_event,
        mock_opensearch,
        mock_lambda_context,
        snapshot: Snapshot,
    ):
        """Test handler reports failure when S3 event payload is missing a bucket name."""
        payload = json.loads(example_sqs_event["Records"][0]["body"])
        del payload["detail"]["bucket"]["name"]
        example_sqs_event["Records"][0]["body"] = json.dumps(payload)

        resp = lambda_function.handler(example_sqs_event, mock_lambda_context)

        assert resp == {
            "batchItemFailures": [{"itemIdentifier": example_sqs_event["Records"][0]["messageId"]}]
        }
        snapshot.assert_match(
            _serialize_snapshot_value(resp),
            "handler_fails_when_event_has_no_bucket_result.json",
        )

    def test_handler_saves_metadata_when_no_relevant_schematron_fields(
        self,
        example_sqs_event,
        mock_aws_setup,
        mock_opensearch,
        mocker,
        mock_lambda_context,
        snapshot,
    ):
        """Test handler saves TTC metadata output when no relevant Schematron fields are found."""
        mocker.patch(
            "text_to_code_lambda.lambda_function._load_schematron_data_fields", return_value=[]
        )

        resp = lambda_function.handler(example_sqs_event, mock_lambda_context)
        assert resp == {"batchItemFailures": []}

        ttc_output = _get_serialized_object(f"{TTC_OUTPUT_PREFIX}{mock_aws_setup.persistence_id}")
        snapshot.assert_match(ttc_output, "no_relevant_schematron_fields_ttc_output.json")

        ttc_metadata_output = _get_serialized_object(
            f"{TTC_METADATA_PREFIX}{mock_aws_setup.persistence_id.removesuffix('.xml')}.json"
        )
        snapshot.assert_match(
            ttc_metadata_output, "no_relevant_schematron_fields_metadata_output.json"
        )

    def test_handler_continues_processing_after_record_exception(
        self,
        example_sqs_event,
        mocker,
        mock_opensearch,
        mock_lambda_context,
        snapshot: Snapshot,
    ):
        """Test handler continues processing remaining records when one record raises an exception."""
        example_sqs_event["Records"].append(json.loads(json.dumps(example_sqs_event["Records"][0])))
        example_sqs_event["Records"][1]["messageId"] = "second-message-id"

        process_record_mock = mocker.patch(
            "text_to_code_lambda.lambda_function.process_record",
            side_effect=[Exception("boom"), None],
        )
        passthrough_output_mock = mocker.patch(
            "text_to_code_lambda.lambda_function._write_ttc_exception_passthrough_output",
            return_value=False,
        )

        resp = lambda_function.handler(example_sqs_event, mock_lambda_context)

        assert process_record_mock.call_count == EXPECTED_EXCEPTION_RESULTS
        assert passthrough_output_mock.call_count == 1
        assert resp == {
            "batchItemFailures": [{"itemIdentifier": example_sqs_event["Records"][0]["messageId"]}]
        }
        snapshot.assert_match(
            _serialize_snapshot_value(resp),
            "handler_continues_processing_after_record_exception_result.json",
        )
        assert mock_opensearch.search.call_count == 0

    def test_handler_returns_failures_when_all_records_raise(
        self,
        example_sqs_event,
        mocker,
        mock_opensearch,
        mock_lambda_context,
        snapshot: Snapshot,
    ):
        """Test handler returns aggregated failures when all records raise exceptions."""
        example_sqs_event["Records"].append(json.loads(json.dumps(example_sqs_event["Records"][0])))
        example_sqs_event["Records"][0]["messageId"] = "first-message-id"
        example_sqs_event["Records"][1]["messageId"] = "second-message-id"

        process_record_mock = mocker.patch(
            "text_to_code_lambda.lambda_function.process_record",
            side_effect=[Exception("first failure"), Exception("second failure")],
        )
        passthrough_output_mock = mocker.patch(
            "text_to_code_lambda.lambda_function._write_ttc_exception_passthrough_output",
            return_value=False,
        )

        resp = lambda_function.handler(example_sqs_event, mock_lambda_context)

        assert process_record_mock.call_count == EXPECTED_EXCEPTION_RESULTS
        assert passthrough_output_mock.call_count == EXPECTED_EXCEPTION_RESULTS
        assert resp == {
            "batchItemFailures": [
                {"itemIdentifier": "first-message-id"},
                {"itemIdentifier": "second-message-id"},
            ]
        }
        snapshot.assert_match(
            _serialize_snapshot_value(resp),
            "handler_returns_failures_when_all_records_raise_result.json",
        )
        assert mock_opensearch.search.call_count == 0

    def test_handler_writes_ttc_exception_passthrough_output_when_record_exception_has_recoverable_persistence_id(
        self,
        example_sqs_event,
        mock_aws_setup,
        mocker,
        mock_opensearch,
        mock_lambda_context,
        snapshot,
    ):
        """Test handler writes passthrough TTC output when a record exception has a recoverable persistence ID."""
        process_record_mock = mocker.patch(
            "text_to_code_lambda.lambda_function.process_record",
            side_effect=Exception("boom"),
        )

        resp = lambda_function.handler(example_sqs_event, mock_lambda_context)

        assert process_record_mock.call_count == 1
        assert resp == {"batchItemFailures": []}

        ttc_output = _get_serialized_object(f"{TTC_OUTPUT_PREFIX}{mock_aws_setup.persistence_id}")
        snapshot.assert_match(ttc_output, "record_exception_id_ttc_output.json")

        ttc_metadata_output = _get_serialized_object(
            f"{TTC_METADATA_PREFIX}{mock_aws_setup.persistence_id.removesuffix('.xml')}.json"
        )
        snapshot.assert_match(ttc_metadata_output, "record_exception_id_metadata_output.json")

    def test_handler_returns_failure_when_ttc_exception_passthrough_write_fails(
        self,
        example_sqs_event,
        mocker,
        mock_opensearch,
        mock_lambda_context,
        snapshot: Snapshot,
    ):
        """Test handler returns failure when TTC exception passthrough output cannot be written."""
        process_record_mock = mocker.patch(
            "text_to_code_lambda.lambda_function.process_record",
            side_effect=Exception("boom"),
        )
        save_outputs_mock = mocker.patch(
            "text_to_code_lambda.lambda_function._save_outputs",
            side_effect=Exception("save failed"),
        )

        resp = lambda_function.handler(example_sqs_event, mock_lambda_context)

        assert process_record_mock.call_count == 1
        assert save_outputs_mock.call_count == 1
        assert resp == {
            "batchItemFailures": [{"itemIdentifier": example_sqs_event["Records"][0]["messageId"]}]
        }
        snapshot.assert_match(
            _serialize_snapshot_value(resp),
            "handler_returns_failure_when_ttc_exception_passthrough_write_fails_result.json",
        )
        assert mock_opensearch.search.call_count == 0

    def test_handler_returns_failure_when_record_exception_has_empty_body(
        self,
        example_sqs_event,
        mocker,
        mock_opensearch,
        mock_lambda_context,
        snapshot: Snapshot,
    ):
        """Test handler returns failure when a record exception cannot produce passthrough output from an empty body."""
        example_sqs_event["Records"][0]["body"] = None

        process_record_mock = mocker.patch(
            "text_to_code_lambda.lambda_function.process_record",
            side_effect=Exception("boom"),
        )

        resp = lambda_function.handler(example_sqs_event, mock_lambda_context)

        assert process_record_mock.call_count == 1
        assert resp == {
            "batchItemFailures": [{"itemIdentifier": example_sqs_event["Records"][0]["messageId"]}]
        }
        snapshot.assert_match(
            _serialize_snapshot_value(resp),
            "handler_returns_failure_when_record_exception_has_empty_body_result.json",
        )
        assert mock_opensearch.search.call_count == 0

    def test_handler_continues_when_selected_candidate_is_none(
        self,
        example_sqs_event,
        mock_aws_setup,
        mock_opensearch,
        mocker,
        mock_lambda_context,
        snapshot,
    ):
        """Test handler skips embedding and OpenSearch when no candidate is selected."""
        mocker.patch(
            "text_to_code.services.evaluator.select_relevant_text",
            return_value=None,
        )

        retriever_embed_mock = mocker.patch.object(lambda_function, "embed")
        reranker_mock = mocker.patch.object(
            lambda_function,
            "rerank",
        )

        resp = lambda_function.handler(example_sqs_event, mock_lambda_context)

        assert resp == {"batchItemFailures": []}

        retriever_embed_mock.assert_not_called()
        reranker_mock.assert_not_called()
        assert mock_opensearch.search.call_count == 0

        ttc_output = _get_serialized_object(f"{TTC_OUTPUT_PREFIX}{mock_aws_setup.persistence_id}")
        snapshot.assert_match(ttc_output, "continues_selected_candidate_none_ttc_output.json")

        ttc_metadata_output = _get_serialized_object(
            f"{TTC_METADATA_PREFIX}{mock_aws_setup.persistence_id.removesuffix('.xml')}.json"
        )
        snapshot.assert_match(
            ttc_metadata_output, "continues_selected_candidate_none_metadata_output.json"
        )

    def test_handler_adds_unmatched_error_when_selected_candidate_has_no_opensearch_hits(
        self,
        example_sqs_event,
        mock_aws_setup,
        mock_opensearch,
        mocker,
        mock_lambda_context,
        snapshot,
    ):
        """Test handler records unmatched errors when a selected candidate has no OpenSearch hits."""
        selected_candidate = Candidate(
            value="weed allergen mix 3", xpath=LabXPaths.CODE_DISPLAY_NAME
        )

        mocker.patch(
            "text_to_code.services.evaluator.select_relevant_text",
            return_value=selected_candidate,
        )

        empty_opensearch_scores = OpenSearchResult(
            took=0,
            timed_out=False,
            _shards=OpenSearchShards(total=0, successful=0, skipped=0, failed=0),
            hits=OpenSearchHits(total={}, hits=[]),
        )

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

        assert resp == {"batchItemFailures": []}

        assert mock_opensearch.search.call_count == 0
        assert reranker_mock.call_count == 0

        ttc_output = _get_serialized_object(f"{TTC_OUTPUT_PREFIX}{mock_aws_setup.persistence_id}")
        snapshot.assert_match(ttc_output, "no_opensearch_hits_ttc_output.json")

        ttc_metadata_output = _get_serialized_object(
            f"{TTC_METADATA_PREFIX}{mock_aws_setup.persistence_id.removesuffix('.xml')}.json"
        )
        snapshot.assert_match(ttc_metadata_output, "no_opensearch_hits_none_metadata_output.json")

    def test_handler_malformed_eicr_with_no_schematron_issues(
        self,
        example_sqs_event,
        mock_aws_setup_malformed_eicr_no_relevant_schematron,
        mock_lambda_context,
        snapshot,
    ):
        resp = lambda_function.handler(example_sqs_event, mock_lambda_context)
        assert resp == {"batchItemFailures": []}

        ttc_output = _get_serialized_object(
            f"{TTC_OUTPUT_PREFIX}{mock_aws_setup_malformed_eicr_no_relevant_schematron.persistence_id}"
        )
        snapshot.assert_match(
            ttc_output, "malformed_eicr_with_no_schematron_issues_ttc_output.json"
        )

        ttc_metadata_output = _get_serialized_object(
            f"{TTC_METADATA_PREFIX}{mock_aws_setup_malformed_eicr_no_relevant_schematron.persistence_id.removesuffix('.xml')}.json"
        )
        snapshot.assert_match(
            ttc_metadata_output, "malformed_eicr_with_no_schematron_issues_ttc_metadata_output.json"
        )

    def test_handler_reranker_returns_empty(
        self,
        example_sqs_event,
        mock_aws_setup,
        mock_lambda_context,
        snapshot,
        mocker,
        mock_opensearch,
    ):

        mocker.patch(
            "text_to_code_lambda.lambda_function.rerank",
            return_value=[],
        )

        resp = lambda_function.handler(example_sqs_event, mock_lambda_context)
        assert resp == {"batchItemFailures": []}

        ttc_output = _get_serialized_object(f"{TTC_OUTPUT_PREFIX}{mock_aws_setup.persistence_id}")
        snapshot.assert_match(ttc_output, "reranker_returns_empty_ttc_output.json")

        ttc_metadata_output = _get_serialized_object(
            f"{TTC_METADATA_PREFIX}{mock_aws_setup.persistence_id.removesuffix('.xml')}.json"
        )
        snapshot.assert_match(
            ttc_metadata_output, "reranker_returns_empty_ttc_metadata_output.json"
        )
