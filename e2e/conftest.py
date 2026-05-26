from collections.abc import Iterator
from unittest.mock import MagicMock, patch

import pytest

from text_to_code_lambda import lambda_function


@pytest.fixture(autouse=True)
def reset_opensearch_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    """Reset cached OpenSearch client before every test."""
    monkeypatch.setattr(lambda_function, "_cached_opensearch_client", None, raising=False)


@pytest.fixture(scope="function")
def mock_opensearch() -> Iterator[MagicMock]:
    """Mock OpenSearch client.

    We have to use MagicMock here instead of moto because
    moto's mocked version of OpenSearch does not support the search functionality,
    only the creation and deletion of indices.
    """
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

    with patch(
        "lambda_handler.create_opensearch_client",
        return_value=opensearch_client,
    ):
        yield opensearch_client
