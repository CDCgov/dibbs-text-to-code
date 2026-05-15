import json

from shared_models import Code
from text_to_code.services.result_cache import get_cached_result

RESULT_CACHE_INDEX_NAME = "test-result-cache"


def patch_opensearch_client(monkeypatch):
    mock_client = object()

    def mock_get() -> dict:
        return {
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

    monkeypatch.setattr(mock_client, "get", mock_get)
    return mock_client


class TestResultCacheAPIs:
    def test_get(self, monkeypatch):
        mock_client = patch_opensearch_client(monkeypatch)
        cached_result = get_cached_result(
            mock_client, RESULT_CACHE_INDEX_NAME, os_doc_id="1357924680"
        )
        assert cached_result is not None
        assert cached_result.cache_key == "1357924680"
        assert cached_result.text == "Screening urine fentanyl detection"
