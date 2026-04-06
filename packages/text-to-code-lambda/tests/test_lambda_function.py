import json
from datetime import UTC
from datetime import datetime

import pytest

import lambda_handler
from conftest import S3_BUCKET
from conftest import TTC_METADATA_PREFIX
from conftest import TTC_OUTPUT_PREFIX
from shared_models import Candidate
from shared_models import CdaInstanceIdentifier
from shared_models import Code
from shared_models import DataField
from shared_models import EICRMetadata
from shared_models import LabXPaths
from shared_models import NonstandardCodeReplacement
from shared_models import OpenSearchHit
from shared_models import OpenSearchHits
from shared_models import OpenSearchHitSource
from shared_models import OpenSearchResult
from shared_models import OpenSearchShards
from shared_models import S3Location
from shared_models import SchematronErrorDetail
from shared_models import SortedRank
from shared_models import TTCOutput
from text_to_code.models.eicr import TTCMetadata
from text_to_code_lambda import lambda_function

EXPECTED_ORDERED_ERRORS = 1
EXPECTED_EXCEPTION_RESULTS = 2
EXPECTED_RERANKER_SCORE = 0.83


@pytest.mark.time_machine(datetime(2026, 1, 1, 1, 1, 0, 0, tzinfo=UTC), tick=False)
class TestHandler:
    def test_handler_success(self, example_sqs_event, mock_aws_setup, mock_opensearch, mocker):
        """Test handler with no failures."""
        resp = lambda_function.handler(example_sqs_event, {})
        assert resp == {
            "statusCode": 200,
            "message": "TTC processed successfully!",
            "num_success_eicrs": 1,
        }

        # Assert that the TTC output was saved to S3
        ttc_output = json.loads(
            lambda_handler.get_file_content_from_s3_to_json(
                bucket_name=S3_BUCKET,
                object_key=f"{TTC_OUTPUT_PREFIX}{mock_aws_setup.persistence_id}",
            )
        )
        actual = TTCOutput(**ttc_output).model_dump_json()
        expected = TTCOutput(
            message=None,
            persistance_id=mock_aws_setup.persistence_id,
            nonstandard_codes=[
                NonstandardCodeReplacement(
                    schematron_error_xpath="/ClinicalDocument/component[1]/structuredBody[1]/component[1]/section[1]/entry[1]/observation[1]",
                    field_type=DataField.LAB_TEST_NAME_ORDERED,
                    new_translation=Code(
                        code="109224-6",
                        code_system="http://loinc.org",
                        code_system_name="LOINC",
                        display_name="Weed Allergen Mix 3 (Mugwort+Goosefoot or Lambs quarters+English plantain+Goldenrod+Nettle) IgE Ab [Measurement] in Serum",
                        original_text="A custom code in display name.",
                    ),
                )
            ],
        ).model_dump_json()

        assert actual == expected

        # Assert that the TTC metadata output was saved to S3 with the expected content
        ttc_metadata_output = json.loads(
            lambda_handler.get_file_content_from_s3_to_json(
                bucket_name=S3_BUCKET,
                object_key=f"{TTC_METADATA_PREFIX}{mock_aws_setup.persistence_id}",
            )
        )
        actual = TTCMetadata(**ttc_metadata_output).model_dump_json()
        expected = TTCMetadata(
            persistance_id=mock_aws_setup.persistence_id,
            message=None,
            eicr_metadata=EICRMetadata(
                eicr_id=CdaInstanceIdentifier(
                    root="c8516bdc-8bb2-40aa-8dae-20a77546488f",
                    extension=None,
                ),
                eicr_vendor="Test eCR Vendor Name",
            ),
            schematron_errors=[
                SchematronErrorDetail(
                    field=DataField.LAB_TEST_NAME_ORDERED,
                    error="Text to Code: Lab Test Name Ordered does not have a @code attribute",
                    error_message="Text to Code: Lab Test Name Ordered does not have a @code attribute",
                    error_context="/ClinicalDocument/component[1]/structuredBody[1]/component[1]/section[1]/entry[1]/observation[1]",
                    error_test=" not(cda:code) or cda:code/@code or cda:code/cda:translation/@code",
                    error_id=None,
                    candidate=Candidate(
                        value="A custom code in display name.",
                        xpath=LabXPaths.CODE_DISPLAY_NAME,
                    ),
                    opensearch_retrieved_scores=OpenSearchResult(
                        took=57,
                        timed_out=False,
                        _shards=OpenSearchShards(
                            total=1, successful=True, skipped=False, failed=False
                        ),
                        hits=OpenSearchHits(
                            total={"value": 3},
                            hits=[
                                OpenSearchHit(
                                    _index="ttc_index",
                                    _id="rbLli5wBhppl0u9qtwLN",
                                    _score=0.95,
                                    _source=OpenSearchHitSource(
                                        id=0,
                                        loinc_code="109224-6",
                                        loinc_name_type="Long Common Name",
                                        description="Weed Allergen Mix 3 (Mugwort+Goosefoot or Lambs quarters+English plantain+Goldenrod+Nettle) IgE Ab [Measurement] in Serum",
                                        loinc_type="Order",
                                        s3=S3Location(
                                            bucket="dibbs-ttc",
                                            key="ingestion/loinc_lab_names_intfloat_e5-large-v2_20251008_00000.jsonl",
                                        ),
                                    ),
                                ),
                                OpenSearchHit(
                                    _index="ttc_index",
                                    _id="123455wBhppl0u9qtABC",
                                    _score=0.88,
                                    _source=OpenSearchHitSource(
                                        id=1,
                                        loinc_code="82041-5",
                                        loinc_name_type="Short Name",
                                        description="Weed Allerg Mix3 IgE Qn",
                                        loinc_type="Order",
                                        s3=S3Location(
                                            bucket="dibbs-ttc",
                                            key="ingestion/loinc_lab_names_intfloat_e5-large-v2_20251008_00000.jsonl",
                                        ),
                                    ),
                                ),
                                OpenSearchHit(
                                    _index="ttc_index",
                                    _id="123455wBhppl0u9qtABC",
                                    _score=0.65,
                                    _source=OpenSearchHitSource(
                                        id=4,
                                        loinc_code="15273-6",
                                        loinc_name_type="Fully-Specified Name",
                                        description="(Artemisia vulgaris+Chenopodium album+Plantago lanceolata+Solidago virgaurea+Urtica dioica) Ab.IgE:PrThr:Pt:Ser:Ord:Multidisk",
                                        loinc_type="Both",
                                        s3=S3Location(
                                            bucket="dibbs-ttc",
                                            key="ingestion/loinc_lab_names_intfloat_e5-large-v2_20251008_00000.jsonl",
                                        ),
                                    ),
                                ),
                            ],
                        ),
                    ),
                    reranker_processed_results=[
                        SortedRank(
                            code_string="Weed Allergen Mix 3 (Mugwort+Goosefoot or Lambs quarters+English plantain+Goldenrod+Nettle) IgE Ab [Measurement] in Serum",
                            score=0.009812851436436176,
                        ),
                        SortedRank(
                            code_string="(Artemisia vulgaris+Chenopodium album+Plantago lanceolata+Solidago virgaurea+Urtica dioica) Ab.IgE:PrThr:Pt:Ser:Ord:Multidisk",
                            score=0.009436368942260742,
                        ),
                        SortedRank(
                            code_string="Weed Allerg Mix3 IgE Qn",
                            score=0.009018019773066044,
                        ),
                    ],
                    new_translation=Code(
                        code="109224-6",
                        code_system="http://loinc.org",
                        code_system_name="LOINC",
                        display_name="Weed Allergen Mix 3 (Mugwort+Goosefoot or Lambs quarters+English plantain+Goldenrod+Nettle) IgE Ab [Measurement] in Serum",
                        original_text="A custom code in display name.",
                    ),
                )
            ],
            processed_at=datetime(2026, 1, 1, 1, 1, 0, 0, tzinfo=UTC),
        ).model_dump_json()

        assert actual == expected

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
