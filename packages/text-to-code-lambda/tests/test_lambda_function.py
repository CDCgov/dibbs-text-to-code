import json
import os
from datetime import UTC, datetime

import pytest
from pytest_snapshot.plugin import Snapshot

import lambda_handler
from lambda_handler.models import (
    OpenSearchHit,
    OpenSearchHits,
    OpenSearchHitSource,
    OpenSearchResult,
    OpenSearchShards,
)
from shared_models import Code
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


@pytest.mark.time_machine(datetime(2026, 1, 1, 1, 1, 0, 0, tzinfo=UTC), tick=False)
class TestHandler:
    def test_handler_success_no_cache_hit(
        self,
        example_sqs_event,
        mock_aws_setup,
        mock_opensearch,
        snapshot: Snapshot,
        mock_lambda_context,
        mocker,
    ):
        """Test handler with no failures when the result cache misses."""
        # We can directly mock the result cache's return value, since we're
        # testing the lambda's logic, not the result cache's
        mocker.patch("text_to_code_lambda.lambda_function.get_cached_result", return_value=None)

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
        assert resp == {
            "statusCode": 200,
            "message": "TTC processed successfully!",
            "num_success_eicrs": 1,
        }

        ttc_output = _get_serialized_object(f"{TTC_OUTPUT_PREFIX}{mock_aws_setup.persistence_id}")
        snapshot.assert_match(ttc_output, "handler_success_ttc_output.json")

        ttc_metadata_output = _get_serialized_object(
            f"{TTC_METADATA_PREFIX}{mock_aws_setup.persistence_id.removesuffix('.xml')}.json"
        )
        snapshot.assert_match(ttc_metadata_output, "handler_success_ttc_metadata_output.json")

    def test_handler_success_using_result_cache(
        self,
        example_sqs_event,
        mock_aws_setup,
        mock_opensearch,
        snapshot: Snapshot,
        mock_lambda_context,
        mocker,
    ):
        """Test handler with no failures when the result cache hits."""
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

        opensearch_retrieved_scores = OpenSearchResult(
            hits=OpenSearchHits(
                hits=[
                    OpenSearchHit(
                        id="rbLli5wBhppl0u9qtwLN",
                        index="ttc_index",
                        score=0.95,
                        source=OpenSearchHitSource(
                            description="Weed Allergen Mix 3 (Mugwort+Goosefoot or Lambs quarters+English plantain+Goldenrod+Nettle) IgE Ab [Measurement] in Serum",
                            id=0,
                            loinc_code="109224-6",
                            loinc_name_type="Long Common Name",
                            loinc_type="Order",
                        ),
                    ),
                    OpenSearchHit(
                        id="123455wBhppl0u9qtABC",
                        index="ttc_index",
                        score=0.88,
                        source=OpenSearchHitSource(
                            description="Weed Allerg Mix3 IgE Qn",
                            id=1,
                            loinc_code="82041-5",
                            loinc_name_type="Short Name",
                            loinc_type="Order",
                        ),
                    ),
                    OpenSearchHit(
                        id="123455wBhppl0u9qtABC",
                        index="ttc_index",
                        score=0.65,
                        source=OpenSearchHitSource(
                            description="(Artemisia vulgaris+Chenopodium album+Plantago lanceolata+Solidago virgaurea+Urtica dioica) Ab.IgE:PrThr:Pt:Ser:Ord:Multidisk",
                            id=4,
                            loinc_code="15273-6",
                            loinc_name_type="Fully-Specified Name",
                            loinc_type="Both",
                        ),
                    ),
                ],
                total={"value": 3},
            ),
            _shards={"failed": 0, "skipped": 0, "successful": 1, "total": 1},
            timed_out=False,
            took=57,
        )

        mocker.patch(
            "text_to_code_lambda.lambda_function.get_cached_result",
            return_value={
                "index": "ttc-result-cache",
                "id": "13579246680",
                "version": "1.0.0",
                "seq_no": "2",
                "primary_term": "3",
                "found": True,
                "routing": "",
                "source": {
                    "cache_key": "1357924680",
                    "text": " A custom code in display name ",
                    "data_field": "Lab Test Name Ordered",
                    "loinc_code": Code(
                        code="82041-5",
                        code_system="2.16.840.1.113883.6.1",
                        code_system_name="LOINC",
                        display_name="Weed Allerg Mix3 IgE Qn",
                    ),
                    "search_score": 0.88,
                    "reranker_score": 7127664685249329,
                    "opensearch_retrieved_scores": opensearch_retrieved_scores,
                    "reranker_processed_results": {"results": ranked_results},
                    "cached_at": "2026-05-15T18:14:45.020655+00:00",
                },
                "fields": {},
            },
        )

        resp = lambda_function.handler(example_sqs_event, mock_lambda_context)
        assert resp == {
            "statusCode": 200,
            "message": "TTC processed successfully!",
            "num_success_eicrs": 1,
        }

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
        assert resp == {
            "statusCode": 200,
            "message": "TTC processed successfully!",
            "num_success_eicrs": 0,
        }
        assert resp["num_success_eicrs"] == 0
        assert mock_opensearch.search.call_count == expected_num_errors

    def test_handler_with_empty_body(
        self, example_sqs_event, caplog_warning, mock_opensearch, mock_lambda_context
    ):
        """Test handler with an empty SQS body."""
        example_sqs_event["Records"][0]["body"] = None
        expected_num_errors = 0
        resp = lambda_function.handler(example_sqs_event, mock_lambda_context)
        assert "Empty SQS body" in caplog_warning.text
        assert resp == {
            "statusCode": 200,
            "message": "TTC processed successfully!",
            "num_success_eicrs": 1,
        }
        assert mock_opensearch.search.call_count == expected_num_errors

    def test_handler_fails_when_event_has_no_bucket(
        self, example_sqs_event, mock_opensearch, mock_lambda_context
    ):
        """Test handler reports failure when S3 event payload is missing a bucket name."""
        payload = json.loads(example_sqs_event["Records"][0]["body"])
        del payload["detail"]["bucket"]["name"]
        example_sqs_event["Records"][0]["body"] = json.dumps(payload)

        resp = lambda_function.handler(example_sqs_event, mock_lambda_context)

        assert resp["num_failure_eicrs"] == 1
        assert resp["num_success_eicrs"] == 0
        assert "No bucket name found" in resp["failures"][0]["error"]

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
        assert resp == {
            "statusCode": 200,
            "message": "TTC processed successfully!",
            "num_success_eicrs": 1,
        }

        ttc_output = _get_serialized_object(f"{TTC_OUTPUT_PREFIX}{mock_aws_setup.persistence_id}")
        snapshot.assert_match(ttc_output, "no_relevant_schematron_fields_ttc_output.json")

        ttc_metadata_output = _get_serialized_object(
            f"{TTC_METADATA_PREFIX}{mock_aws_setup.persistence_id.removesuffix('.xml')}.json"
        )
        snapshot.assert_match(
            ttc_metadata_output, "no_relevant_schematron_fields_metadata_output.json"
        )

    def test_handler_continues_processing_after_record_exception(
        self, example_sqs_event, mocker, mock_opensearch, mock_lambda_context
    ):
        """Test handler continues processing remaining records when one record raises an exception."""
        example_sqs_event["Records"].append(json.loads(json.dumps(example_sqs_event["Records"][0])))
        example_sqs_event["Records"][1]["messageId"] = "second-message-id"

        process_record_mock = mocker.patch(
            "text_to_code_lambda.lambda_function.process_record",
            side_effect=[Exception("boom"), None],
        )

        resp = lambda_function.handler(example_sqs_event, mock_lambda_context)

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
        self, example_sqs_event, mocker, mock_opensearch, mock_lambda_context
    ):
        """Test handler returns aggregated failures when all records raise exceptions."""
        example_sqs_event["Records"].append(json.loads(json.dumps(example_sqs_event["Records"][0])))
        example_sqs_event["Records"][0]["messageId"] = "first-message-id"
        example_sqs_event["Records"][1]["messageId"] = "second-message-id"

        process_record_mock = mocker.patch(
            "text_to_code_lambda.lambda_function.process_record",
            side_effect=[Exception("first failure"), Exception("second failure")],
        )

        resp = lambda_function.handler(example_sqs_event, mock_lambda_context)

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
        assert resp == {
            "statusCode": 200,
            "message": "TTC processed successfully!",
            "num_success_eicrs": 1,
        }

        ttc_output = _get_serialized_object(f"{TTC_OUTPUT_PREFIX}{mock_aws_setup.persistence_id}")
        snapshot.assert_match(ttc_output, "record_exception_id_ttc_output.json")

        ttc_metadata_output = _get_serialized_object(
            f"{TTC_METADATA_PREFIX}{mock_aws_setup.persistence_id.removesuffix('.xml')}.json"
        )
        snapshot.assert_match(ttc_metadata_output, "record_exception_id_metadata_output.json")

    def test_handler_returns_failure_when_record_exception_has_empty_body(
        self,
        example_sqs_event,
        mocker,
        mock_opensearch,
        mock_lambda_context,
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
            "statusCode": 200,
            "message": "TTC processed with some failures!",
            "failures": [
                {"message_id": example_sqs_event["Records"][0]["messageId"], "error": "boom"}
            ],
            "num_failure_eicrs": 1,
            "num_success_eicrs": 0,
        }
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

        assert resp == {
            "statusCode": 200,
            "message": "TTC processed successfully!",
            "num_success_eicrs": 1,
        }

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

        assert resp == {
            "statusCode": 200,
            "message": "TTC processed successfully!",
            "num_success_eicrs": 1,
        }

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
        assert resp == {
            "statusCode": 200,
            "message": "TTC processed successfully!",
            "num_success_eicrs": 1,
        }

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
        assert resp == {
            "statusCode": 200,
            "message": "TTC processed successfully!",
            "num_success_eicrs": 1,
        }

        ttc_output = _get_serialized_object(f"{TTC_OUTPUT_PREFIX}{mock_aws_setup.persistence_id}")
        snapshot.assert_match(ttc_output, "reranker_returns_empty_ttc_output.json")

        ttc_metadata_output = _get_serialized_object(
            f"{TTC_METADATA_PREFIX}{mock_aws_setup.persistence_id.removesuffix('.xml')}.json"
        )
        snapshot.assert_match(
            ttc_metadata_output, "reranker_returns_empty_ttc_metadata_output.json"
        )
