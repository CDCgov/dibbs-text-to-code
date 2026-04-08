import os
from unittest.mock import MagicMock
from unittest.mock import patch

import pytest

from shared_models import EICR_INPUT_PREFIX
from shared_models import S3_BUCKET
from shared_models import SCHEMATRON_ERROR_PREFIX
from shared_models import TTC_INPUT_PREFIX
from shared_models import TTC_METADATA_PREFIX
from shared_models import TTC_OUTPUT_PREFIX
from text_to_code_lambda import lambda_function

AWS_REGION = "us-east-1"
AWS_ACCESS_KEY_ID = "test_access_key_id"
AWS_SECRET_ACCESS_KEY = "test_secret_access_key"  # noqa: S105
OPENSEARCH_ENDPOINT_URL = "https://test-opensearch-endpoint.com"
TEST_PERSISTENCE_ID = "2025/09/03/1-5f84c7a5-91d7f5c6a2b7c9e08f0d1234"


def pytest_configure() -> None:
    """Configure env variables for pytest."""
    os.environ["S3_BUCKET"] = S3_BUCKET
    os.environ["EICR_INPUT_PREFIX"] = EICR_INPUT_PREFIX
    os.environ["SCHEMATRON_ERROR_PREFIX"] = SCHEMATRON_ERROR_PREFIX
    os.environ["TTC_INPUT_PREFIX"] = TTC_INPUT_PREFIX
    os.environ["TTC_OUTPUT_PREFIX"] = TTC_OUTPUT_PREFIX
    os.environ["TTC_METADATA_PREFIX"] = TTC_METADATA_PREFIX
    os.environ["AWS_REGION"] = AWS_REGION
    os.environ["AWS_ACCESS_KEY_ID"] = AWS_ACCESS_KEY_ID
    os.environ["AWS_SECRET_ACCESS_KEY"] = AWS_SECRET_ACCESS_KEY
    os.environ["OPENSEARCH_ENDPOINT_URL"] = OPENSEARCH_ENDPOINT_URL


@pytest.fixture(autouse=True)
def reset_opensearch_cache() -> None:
    """Reset cached OpenSearch client before every test."""
    lambda_function._cached_opensearch_client = None


@pytest.fixture(scope="function")
def mock_opensearch() -> None:
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
