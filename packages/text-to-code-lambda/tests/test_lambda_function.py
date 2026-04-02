import json

import pytest

import lambda_handler
from conftest import S3_BUCKET
from conftest import TTC_METADATA_PREFIX
from conftest import TTC_OUTPUT_PREFIX
from text_to_code_lambda import lambda_function

EXPECTED_RESULTED_ERRORS = 2
EXPECTED_ORDERED_ERRORS = 2
EXPECTED_EXCEPTION_RESULTS = 2
EXPECTED_RERANKER_SCORE = 0.83


class TestHandler:
    def test_handler_success(self, example_sqs_event, mock_aws_setup, mock_opensearch, mocker):
        """Test handler with no failures."""
        selected_candidate = {
            "value": "weed allergen mix 3",
            "confidence": 1.0,
        }

        mocker.patch(
            "text_to_code.services.evaluator.select_relevant_text",
            return_value=type("SelectedCandidate", (), selected_candidate)(),
        )

        resp = lambda_function.handler(example_sqs_event, {})
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
        assert (
            "reranker_processed_results"
            not in ttc_output["schematron_errors"]["Lab Test Name Resulted"][0]
        )
        assert "schematron_error" in ttc_output["schematron_errors"]["Lab Test Name Resulted"][0]
        assert (
            "schematron_error_xpath" in ttc_output["schematron_errors"]["Lab Test Name Resulted"][0]
        )
        assert "field_type" in ttc_output["schematron_errors"]["Lab Test Name Resulted"][0]
        assert "new_translation" in ttc_output["schematron_errors"]["Lab Test Name Resulted"][0]
        assert (
            ttc_output["schematron_errors"]["Lab Test Name Resulted"][0]["field_type"]
            == "Lab Test Name Resulted"
        )
        assert (
            ttc_output["schematron_errors"]["Lab Test Name Resulted"][0]["new_translation"]["code"]
            == "109224-6"
        )
        assert (
            ttc_output["schematron_errors"]["Lab Test Name Resulted"][0]["new_translation"][
                "code_system"
            ]
            == "2.16.840.1.113883.6.1"
        )
        assert (
            ttc_output["schematron_errors"]["Lab Test Name Resulted"][0]["new_translation"][
                "code_system_name"
            ]
            == "LOINC"
        )
        assert (
            ttc_output["schematron_errors"]["Lab Test Name Resulted"][0]["new_translation"][
                "display_name"
            ]
            is not None
        )
        assert (
            ttc_output["schematron_errors"]["Lab Test Name Resulted"][0]["new_translation"][
                "original_text"
            ]
            == "weed allergen mix 3"
        )

        # Assert that the TTC metadata output was saved to S3 with the expected content
        ttc_metadata_output = json.loads(
            lambda_handler.get_file_content_from_s3(
                bucket_name=S3_BUCKET,
                object_key=f"{TTC_METADATA_PREFIX}{mock_aws_setup.persistence_id}",
            )
        )
        assert ttc_metadata_output is not None
        assert ttc_metadata_output["persistence_id"] == mock_aws_setup.persistence_id
        assert "eicr_metadata" in ttc_metadata_output
        assert "schematron_errors" in ttc_metadata_output
        assert "processed_at" in ttc_metadata_output
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
        assert (
            "reranker_processed_results"
            in ttc_metadata_output["schematron_errors"]["Lab Test Name Resulted"][0]
        )
        predicted_candidate = ttc_metadata_output["schematron_errors"]["Lab Test Name Resulted"][0][
            "reranker_processed_results"
        ][0]
        assert predicted_candidate["code_string"] == "Weed Allerg Mix3 IgE Qn"
        assert round(float(predicted_candidate["score"]), 3) == EXPECTED_RERANKER_SCORE

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

    def test_handler_saves_metadata_when_no_relevant_schematron_fields(
        self, example_sqs_event, mock_aws_setup, mock_opensearch, mocker
    ):
        """Test handler saves TTC metadata output when no relevant Schematron fields are found."""
        mocker.patch(
            "text_to_code_lambda.lambda_function._load_schematron_data_fields", return_value=[]
        )

        resp = lambda_function.handler(example_sqs_event, {})
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
                object_key=f"{TTC_METADATA_PREFIX}{mock_aws_setup.persistence_id}",
            )
        )
        assert ttc_metadata_output is not None
        assert ttc_metadata_output["persistence_id"] == mock_aws_setup.persistence_id
        assert (
            ttc_metadata_output["reason_for_skipping"]
            == "No relevant data fields identified from Schematron errors for TTC processing"
        )
        assert "processed_at" in ttc_metadata_output
        assert ttc_metadata_output["eicr_metadata"] == {}
        assert ttc_metadata_output["schematron_errors"] == {}
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

    def test_handler_continues_when_selected_candidate_is_none(
        self, example_sqs_event, mock_aws_setup, mock_opensearch, mocker
    ):
        """Test handler skips embedding and OpenSearch when no candidate is selected."""
        mocker.patch(
            "text_to_code.services.evaluator.select_relevant_text",
            return_value=None,
        )

        retriever_embed_mock = mocker.patch.object(lambda_function.RETRIEVER, "embed")
        reranker_mock = mocker.patch.object(lambda_function.RERANKER, "rerank")

        resp = lambda_function.handler(example_sqs_event, {})

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
        assert ttc_output["persistence_id"] == mock_aws_setup.persistence_id
        assert ttc_output["schematron_errors"]["Lab Test Name Resulted"][0]["candidate"] is None

        ttc_metadata_output = json.loads(
            lambda_handler.get_file_content_from_s3(
                bucket_name=S3_BUCKET,
                object_key=f"{TTC_METADATA_PREFIX}{mock_aws_setup.persistence_id}",
            )
        )
        assert ttc_metadata_output is not None
        assert ttc_metadata_output["persistence_id"] == mock_aws_setup.persistence_id
        assert ttc_metadata_output["schematron_errors"]["Lab Test Name Resulted"] == []
        assert ttc_metadata_output["schematron_errors"]["Lab Test Name Ordered"] == []
