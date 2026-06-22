from collections.abc import Iterator
from unittest.mock import MagicMock, patch

import pytest

from text_to_code_lambda import lambda_function


@pytest.fixture(autouse=True)
def reset_opensearch_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    """Reset cached OpenSearch client before every test."""
    monkeypatch.setattr(lambda_function, "_cached_opensearch_client", None, raising=False)


@pytest.fixture(scope="function")
def mock_opensearch(request: pytest.FixtureRequest) -> Iterator[MagicMock]:
    """Mock OpenSearch client.

    We have to use MagicMock here instead of moto because
    moto's mocked version of OpenSearch does not support the search functionality,
    only the creation and deletion of indices.
    """
    candidates: list[str] = getattr(request, "param", ["dummy"])
    candidate_iter = iter(candidates)

    def build_response(*args, **kwargs) -> dict:  # noqa: ANN002, ANN003
        value = next(candidate_iter)
        return {
            "found": True,
            "_source": {
                "cache_key": "test_cache_key",
                "text": value,
                "data_field": "Lab Test Name Resulted",
                "codeid": 0,
                "loinc_code": {
                    "code": "82041-5",
                    "code_system": "2.16.840.1.113883.6.1",
                    "code_system_name": "LOINC",
                    "display_name": "Weed Allerg Mix3 IgE Qn",
                    "original_text": value,
                },
                "loinc_name_type": "Long Common Name",
                "description": "Weed Allergen Mix 3 (Mugwort+Goosefoot or Lambs quarters+English plantain+Goldenrod+Nettle) IgE Ab [Measurement] in Serum",
                "loinc_type": "Order",
                "s3": {
                    "bucket": "dibbs-ttc",
                    "key": "ingestion/loinc_lab_names_intfloat_e5-large-v2_20251008_00000.jsonl",
                },
                "search_score": 0.9563,
                "reranker_score": 0.6789,
                "opensearch_retrieved_scores": {
                    "took": 234,
                    "timed_out": False,
                    "_shards": {"total": 1, "successful": 1, "failed": 0, "skipped": 0},
                    "hits": {
                        "total": {},
                        "hits": [],
                    },
                },
                "reranker_processed_results": {"results": []},
                "cached_at": "2026-05-15T18:14:45.020655+00:00",
            },
        }

    opensearch_client = MagicMock()

    opensearch_client.search.return_value = {
        "took": 57,
        "timed_out": False,
        "_shards": {"total": 1, "successful": 1, "skipped": 0, "failed": 0},
        "hits": {
            "total": {"value": 3},
            "hits": [
                {
                    "_index": "ttc_index",
                    "_id": "rbLli5wBhppl0u9qtwLN",
                    "_score": 0.95,
                    "_source": {
                        "id": 0,
                        "loinc_code": "109224-6",
                        "loinc_name_type": "Long Common Name",
                        "description": "Weed Allergen Mix 3 (Mugwort+Goosefoot or Lambs quarters+English plantain+Goldenrod+Nettle) IgE Ab [Measurement] in Serum",
                        "loinc_type": "Order",
                        "s3": {
                            "bucket": "dibbs-ttc",
                            "key": "ingestion/loinc_lab_names_intfloat_e5-large-v2_20251008_00000.jsonl",
                        },
                    },
                },
                {
                    "_index": "ttc_index",
                    "_id": "123455wBhppl0u9qtABC",
                    "_score": 0.88,
                    "_source": {
                        "id": 1,
                        "loinc_code": "82041-5",
                        "loinc_name_type": "Short Name",
                        "description": "Weed Allerg Mix3 IgE Qn",
                        "loinc_type": "Order",
                        "s3": {
                            "bucket": "dibbs-ttc",
                            "key": "ingestion/loinc_lab_names_intfloat_e5-large-v2_20251008_00000.jsonl",
                        },
                    },
                },
                {
                    "_index": "ttc_index",
                    "_id": "123455wBhppl0u9qtABC",
                    "_score": 0.65,
                    "_source": {
                        "id": 4,
                        "loinc_code": "15273-6",
                        "loinc_name_type": "Fully-Specified Name",
                        "description": "(Artemisia vulgaris+Chenopodium album+Plantago lanceolata+Solidago virgaurea+Urtica dioica) Ab.IgE:PrThr:Pt:Ser:Ord:Multidisk",
                        "loinc_type": "Both",
                        "s3": {
                            "bucket": "dibbs-ttc",
                            "key": "ingestion/loinc_lab_names_intfloat_e5-large-v2_20251008_00000.jsonl",
                        },
                    },
                },
            ],
        },
    }

    opensearch_client.get.side_effect = build_response
    with patch(
        "lambda_handler.create_opensearch_client",
        return_value=opensearch_client,
    ):
        yield opensearch_client
