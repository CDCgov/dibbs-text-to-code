import json
from unittest.mock import patch

from shared_models import Code
from text_to_code.services.result_cache import get_cached_result

RESULT_CACHE_INDEX_NAME = "test-result-cache"


class TestResultCacheAPIs:
    @patch("text_to_code.services.result_cache.opensearch")
    def test_get(self, mock_opensearch_client):
        mock_client = mock_opensearch_client.return_value
        mock_client.get.return_value = {
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
                "data_field": "field",
                "loinc_code": json.dumps(
                    Code(
                        code_system="2.16.840.1.113883.6.1",
                        code_system_name="LOINC",
                        display_name="fentaNYL [Presence] in Urine by Screen method",
                    )
                ),
                "search_score": 0.9563,
                "reranker_score": 0.6789,
                "cached_at": "2026-05-15T18:14:45.020655+00:00",
            },
            "fields": {},
        }

        cached_result = get_cached_result(mock_client, RESULT_CACHE_INDEX_NAME, "1357924680")

        assert cached_result is not None
        assert cached_result.cache_key == "1357924680"
        assert cached_result.text == "Screening urine fentanyl detection"
