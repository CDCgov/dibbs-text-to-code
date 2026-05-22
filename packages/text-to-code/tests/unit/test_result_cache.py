import json
from unittest.mock import MagicMock

from shared_models import Code
from text_to_code.services.result_cache import get_cached_result, put_new_cached_result

RESULT_CACHE_INDEX_NAME = "test-result-cache"


class TestResultCacheAPIs:
    def test_get_success(self):
        """Tests the Result Cache's GET functionality when the document is present."""
        mock_opensearch_client = MagicMock()
        mock_opensearch_client.get.return_value = {
            "index": RESULT_CACHE_INDEX_NAME,
            "id": "13579246680",
            "version": "1.0.0",
            "seq_no": "2",
            "primary_term": "3",
            "found": True,
            "routing": "",
            "source": {
                "cache_key": "1357924680",
                "text": "Screening urine fentanyl detection",
                "data_field": "Lab Test Name Ordered",
                "loinc_code": json.dumps(
                    Code(
                        code_system="2.16.840.1.113883.6.1",
                        code_system_name="LOINC",
                        display_name="fentaNYL [Presence] in Urine by Screen method",
                    ).__dict__
                ),
                "search_score": 0.9563,
                "reranker_score": 0.6789,
                "cached_at": "2026-05-15T18:14:45.020655+00:00",
            },
            "fields": {},
        }

        cached_result = get_cached_result(
            mock_opensearch_client, RESULT_CACHE_INDEX_NAME, "1357924680"
        )

        assert cached_result is not None
        assert cached_result["cache_key"] == "1357924680"
        assert cached_result["text"] == "Screening urine fentanyl detection"

    def test_get_miss(self):
        """Tests the Result Cache's GET functionality when the document is absent."""
        mock_opensearch_client = MagicMock()
        mock_opensearch_client.get.return_value = {
            "index": RESULT_CACHE_INDEX_NAME,
            "id": "",
            "version": "",
            "seq_no": "",
            "primary_term": "",
            "found": False,
            "routing": "",
            "source": {},
            "fields": {},
        }

        cached_result = get_cached_result(
            mock_opensearch_client, RESULT_CACHE_INDEX_NAME, "1357924680"
        )

        assert cached_result is None

    def test_put_cache_hit_success(self):
        """Tests the Result Cache service's PUT function when the result is created."""
        mock_opensearch_client = MagicMock()
        mock_opensearch_client.index.return_value = {
            "_index": RESULT_CACHE_INDEX_NAME,
            "_id": "a652c34ac12",
            "_version": "1.0.0",
            "result": "created",
        }

        standard_loinc_code = Code(
            code="6299-2",
            code_system="2.16.840.1.113883.6.1",
            code_system_name="LOINC",
            display_name="Urea nitrogen [Mass/volume] in Blood",
        )

        cache_result_created = put_new_cached_result(
            mock_opensearch_client,
            RESULT_CACHE_INDEX_NAME,
            "blood urea nitrogen (BUN)",
            "Lab Test Name Resulted",
            standard_loinc_code,
            0.97771,
            0.8624,
        )

        assert cache_result_created
