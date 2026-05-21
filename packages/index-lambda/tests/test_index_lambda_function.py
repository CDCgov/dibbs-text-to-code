import pytest

from index_lambda import lambda_function

INDEX_NAME = "test-index"
RESULT_CACHE_INDEX_NAME = "test-result-cache-index"
SUCCESS_CODE = 200
THRESHOLD_MS = 250


class MockIndices:
    def __init__(
        self,
        *,
        description_vector_type: str | None = None,
        index_initially_exists: bool = False,
        result_cache_initially_exists: bool = False,
    ) -> None:
        """Mock class for OpenSearch client's indices property."""
        self._exists_calls = {INDEX_NAME: 0, RESULT_CACHE_INDEX_NAME: 0}
        self._initially_exists = {
            INDEX_NAME: index_initially_exists,
            RESULT_CACHE_INDEX_NAME: result_cache_initially_exists,
        }
        self.delete_calls: dict[str, list[str]] = {INDEX_NAME: [], RESULT_CACHE_INDEX_NAME: []}
        self.create_calls: dict[str, list[str]] = {INDEX_NAME: [], RESULT_CACHE_INDEX_NAME: []}
        self.put_settings_calls: dict[str, list[tuple[str, dict]]] = {
            INDEX_NAME: [],
            RESULT_CACHE_INDEX_NAME: [],
        }
        if description_vector_type is not None:
            self.description_vector_type = description_vector_type

    def exists(self, index: str) -> bool:
        """Mock exists method that returns False on the first call and True on subsequent calls to simulate index creation."""
        self._exists_calls[index] += 1
        if self._initially_exists[index]:
            return True
        return self._exists_calls[index] != 1

    def create(self, index: str, body: dict) -> None:
        """Mock create method that tracks calls."""
        self.create_calls[index].append(index)

    def delete(self, index: str) -> None:
        """Mock delete method that tracks calls."""
        self.delete_calls[index].append(index)

    def get(self, index: str) -> dict:
        """Mock get method that returns basic index metadata."""
        return {index: {"aliases": {}, "mappings": {}, "settings": {}}}

    def get_settings(self, index: str) -> dict:
        """Mock get_settings method that returns a dummy settings dictionary."""
        if index == INDEX_NAME:
            return {index: {"settings": {"index": {"knn": "true"}}}}
        if index == RESULT_CACHE_INDEX_NAME:
            return {index: {"settings": {"index": {"knn": "false"}}}}
        raise ValueError(f"Unexpected env var requested: {index}")

    def get_mapping(self, index: str) -> dict:
        """Mock get_mapping method that returns a mapping dictionary."""
        if index == INDEX_NAME:
            return {
                index: {
                    "mappings": {
                        "properties": {
                            "description_vector": {"type": self.description_vector_type},
                        },
                    }
                }
            }
        if index == RESULT_CACHE_INDEX_NAME:
            return {
                index: {
                    "mappings": {
                        "properties": {
                            "cache_key": {"type": "keyword"},
                        }
                    }
                }
            }
        raise ValueError(f"Unexpected env var requested: {index}")

    def put_settings(self, index: str, body: dict) -> None:
        """Mock put_settings method that tracks settings updates."""
        self.put_settings_calls[index].append((index, body))


class MockOpenSearchClient:
    def __init__(
        self,
        *,
        description_vector_type: str | None = None,
        index_initially_exists: bool = False,
        result_cache_initially_exists: bool = False,
    ) -> None:
        """Mock class for OpenSearch client."""
        self.indices = MockIndices(
            description_vector_type=description_vector_type,
            index_initially_exists=index_initially_exists,
            result_cache_initially_exists=result_cache_initially_exists,
        )


def patch_lambda_handler(
    monkeypatch,
    *,
    description_vector_type: str | None = None,
    index_initially_exists: bool = False,
    result_cache_initially_exists: bool = False,
) -> MockOpenSearchClient:
    mock_client = MockOpenSearchClient(
        description_vector_type=description_vector_type,
        index_initially_exists=index_initially_exists,
        result_cache_initially_exists=result_cache_initially_exists,
    )

    def mock_create_aws_auth() -> object:
        """Mock create_aws_auth function that returns a dummy AWS auth object."""
        return object()

    def mock_create_opensearch_client() -> MockOpenSearchClient:
        """Mock create_opensearch_client function that returns a MockOpenSearchClient."""
        return mock_client

    def mock_get_env_variable(name: str) -> str:
        """Mock get_env_variable function that returns the INDEX_NAME for the INDEX_NAME variable."""
        if name == "INDEX_NAME":
            return INDEX_NAME
        if name == "RESULT_CACHE_INDEX_NAME":
            return RESULT_CACHE_INDEX_NAME
        raise ValueError(f"Unexpected env var requested: {name}")

    monkeypatch.setattr(lambda_function.lambda_handler, "create_aws_auth", mock_create_aws_auth)
    monkeypatch.setattr(
        lambda_function.lambda_handler,
        "create_opensearch_client",
        mock_create_opensearch_client,
    )
    monkeypatch.setattr(lambda_function, "get_env_variable", mock_get_env_variable)
    return mock_client


class TestHandler:
    def test_handler_invalid_action(self, monkeypatch, mock_lambda_context):
        """Test handler raises error if given an unknown or invalid action."""
        patch_lambda_handler(monkeypatch, description_vector_type="knn_vector")

        with pytest.raises(ValueError, match="Received unknown action: 'disallowed'"):
            lambda_function.handler({"action": "disallowed"}, mock_lambda_context)

    def test_handler_create_index_success(self, monkeypatch, mock_lambda_context):
        """Test handler creates the vector search index when it does not exist and returns expected response."""
        patch_lambda_handler(monkeypatch, description_vector_type="knn_vector")

        resp = lambda_function.handler({}, mock_lambda_context)

        assert resp["statusCode"] == SUCCESS_CODE
        assert resp["index_name"] == INDEX_NAME
        assert resp["index_exists"] is True
        assert resp["ran_index_creation"] is True
        assert resp["index_settings"] == {INDEX_NAME: {"settings": {"index": {"knn": "true"}}}}
        assert resp["index_mappings"] == {
            INDEX_NAME: {
                "mappings": {
                    "properties": {"description_vector": {"type": "knn_vector"}},
                }
            }
        }

    def test_handler_create_result_cache_success(self, monkeypatch, mock_lambda_context):
        """Test handler returns index metadata when result cache index already exists."""
        patch_lambda_handler(monkeypatch, result_cache_initially_exists=True)

        resp = lambda_function.handler({"action": "create_result_cache"}, mock_lambda_context)

        assert resp["statusCode"] == SUCCESS_CODE
        assert resp["index_name"] == RESULT_CACHE_INDEX_NAME
        assert resp["ran_index_creation"] is False
        assert resp["index_settings"] == {
            RESULT_CACHE_INDEX_NAME: {"settings": {"index": {"knn": "false"}}}
        }
        assert resp["index_mappings"] == {
            RESULT_CACHE_INDEX_NAME: {
                "mappings": {
                    "properties": {
                        "cache_key": {"type": "keyword"},
                    }
                }
            }
        }

    def test_handler_clear_index_deletes_and_recreates(self, monkeypatch, mock_lambda_context):
        """Test clear_index action deletes existing index and recreates it."""
        mock_client = patch_lambda_handler(
            monkeypatch, description_vector_type="knn_vector", index_initially_exists=True
        )

        resp = lambda_function.handler({"action": "clear_index"}, mock_lambda_context)

        assert resp["statusCode"] == SUCCESS_CODE
        assert resp["action"] == "clear_index"
        assert resp["index_deleted"] is True
        assert resp["index_recreated"] is True
        assert mock_client.indices.delete_calls == {
            INDEX_NAME: [INDEX_NAME],
            RESULT_CACHE_INDEX_NAME: [],
        }
        assert mock_client.indices.create_calls == {
            INDEX_NAME: [INDEX_NAME],
            RESULT_CACHE_INDEX_NAME: [],
        }

    def test_handler_clear_result_cache_without_initial_exist(
        self, monkeypatch, mock_lambda_context
    ):
        """Test clear_result_cache action to clear the cache index when it doesn't exist initially."""
        mock_client = patch_lambda_handler(monkeypatch)

        resp = lambda_function.handler({"action": "clear_result_cache"}, mock_lambda_context)

        assert resp["statusCode"] == SUCCESS_CODE
        assert resp["action"] == "clear_result_cache"
        assert resp["index_deleted"] is False
        assert resp["index_recreated"] is True
        assert mock_client.indices.delete_calls == {INDEX_NAME: [], RESULT_CACHE_INDEX_NAME: []}
        assert mock_client.indices.create_calls == {
            INDEX_NAME: [],
            RESULT_CACHE_INDEX_NAME: [RESULT_CACHE_INDEX_NAME],
        }

    def test_handler_clear_index_when_no_existing_index(self, monkeypatch, mock_lambda_context):
        """Test clear_index action when the index doesn't exist yet."""
        mock_client = patch_lambda_handler(monkeypatch, description_vector_type="knn_vector")

        resp = lambda_function.handler({"action": "clear_index"}, mock_lambda_context)

        assert resp["statusCode"] == SUCCESS_CODE
        assert resp["action"] == "clear_index"
        assert resp["index_deleted"] is False
        assert resp["index_recreated"] is True
        assert mock_client.indices.delete_calls == {INDEX_NAME: [], RESULT_CACHE_INDEX_NAME: []}
        assert mock_client.indices.create_calls == {
            INDEX_NAME: [INDEX_NAME],
            RESULT_CACHE_INDEX_NAME: [],
        }

    def test_handler_set_slowlog_updates_index_settings(self, monkeypatch, mock_lambda_context):
        """Test set_slowlog action updates slowlog thresholds and returns index metadata."""
        mock_client = patch_lambda_handler(
            monkeypatch, description_vector_type="knn_vector", index_initially_exists=True
        )

        resp = lambda_function.handler(
            {"action": "set_slowlog", "threshold_ms": THRESHOLD_MS},
            mock_lambda_context,
        )

        assert resp["statusCode"] == SUCCESS_CODE
        assert resp["action"] == "set_slowlog"
        assert resp["threshold_ms"] == THRESHOLD_MS
        assert resp["index"] == {INDEX_NAME: {"aliases": {}, "mappings": {}, "settings": {}}}
        assert resp["settings"] == {INDEX_NAME: {"settings": {"index": {"knn": "true"}}}}
        assert resp["mappings"] == {
            INDEX_NAME: {
                "mappings": {
                    "properties": {"description_vector": {"type": "knn_vector"}},
                }
            }
        }
        assert mock_client.indices.put_settings_calls == {
            INDEX_NAME: [
                (
                    INDEX_NAME,
                    {
                        "index.search.slowlog.threshold.query.warn": f"{THRESHOLD_MS}ms",
                        "index.search.slowlog.threshold.query.info": f"{THRESHOLD_MS}ms",
                        "index.search.slowlog.threshold.fetch.warn": f"{THRESHOLD_MS}ms",
                        "index.search.slowlog.threshold.fetch.info": f"{THRESHOLD_MS}ms",
                    },
                )
            ],
            RESULT_CACHE_INDEX_NAME: [],
        }

    def test_handler_set_result_cache_slowlog(self, monkeypatch, mock_lambda_context):
        """Test result cache can be updated using slowlog action."""
        mock_client = patch_lambda_handler(monkeypatch, result_cache_initially_exists=True)

        resp = lambda_function.handler(
            {"action": "set_result_cache_slowlog", "threshold_ms": THRESHOLD_MS},
            mock_lambda_context,
        )

        assert resp["statusCode"] == SUCCESS_CODE
        assert resp["action"] == "set_result_cache_slowlog"
        assert resp["threshold_ms"] == THRESHOLD_MS
        assert resp["index"] == {
            RESULT_CACHE_INDEX_NAME: {"aliases": {}, "mappings": {}, "settings": {}}
        }
        assert resp["settings"] == {
            RESULT_CACHE_INDEX_NAME: {"settings": {"index": {"knn": "false"}}}
        }
        assert resp["mappings"] == {
            RESULT_CACHE_INDEX_NAME: {
                "mappings": {
                    "properties": {
                        "cache_key": {"type": "keyword"},
                    }
                }
            }
        }
        assert mock_client.indices.put_settings_calls == {
            INDEX_NAME: [],
            RESULT_CACHE_INDEX_NAME: [
                (
                    RESULT_CACHE_INDEX_NAME,
                    {
                        "index.search.slowlog.threshold.query.warn": f"{THRESHOLD_MS}ms",
                        "index.search.slowlog.threshold.query.info": f"{THRESHOLD_MS}ms",
                        "index.search.slowlog.threshold.fetch.warn": f"{THRESHOLD_MS}ms",
                        "index.search.slowlog.threshold.fetch.info": f"{THRESHOLD_MS}ms",
                    },
                )
            ],
        }
