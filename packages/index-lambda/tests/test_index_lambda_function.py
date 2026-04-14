from index_lambda import lambda_function

INDEX_NAME = "test-index"


class MockIndices:
    def __init__(
        self, description_vector_type: str, *, initially_exists: bool = False
    ) -> None:
        """Mock class for OpenSearch client's indices property."""
        self._exists_calls = 0
        self._initially_exists = initially_exists
        self.description_vector_type = description_vector_type
        self.delete_calls: list[str] = []
        self.create_calls: list[str] = []

    def exists(self, index: str) -> bool:
        """Mock exists method that returns False on the first call and True on subsequent calls to simulate index creation."""
        self._exists_calls += 1
        if self._initially_exists:
            return True
        return self._exists_calls != 1

    def create(self, index: str, body: dict) -> None:
        """Mock create method that tracks calls."""
        self.create_calls.append(index)

    def delete(self, index: str) -> None:
        """Mock delete method that tracks calls."""
        self.delete_calls.append(index)

    def get_settings(self, index: str) -> dict:
        """Mock get_settings method that returns a fixed settings dictionary."""
        return {INDEX_NAME: {"settings": {"index": {"knn": "true"}}}}

    def get_mapping(self, index: str) -> dict:
        """Mock get_mapping method that returns a mapping dictionary with the specified description_vector type."""
        return {
            INDEX_NAME: {
                "mappings": {
                    "properties": {
                        "description_vector": {"type": self.description_vector_type},
                    },
                }
            }
        }


class MockOpenSearchClient:
    def __init__(
        self, description_vector_type: str, *, initially_exists: bool = False
    ) -> None:
        """Mock class for OpenSearch client."""
        self.indices = MockIndices(
            description_vector_type, initially_exists=initially_exists
        )


def patch_lambda_handler(
    monkeypatch,
    description_vector_type: str,
    *,
    initially_exists: bool = False,
) -> MockOpenSearchClient:
    mock_client = MockOpenSearchClient(
        description_vector_type, initially_exists=initially_exists
    )

    def mock_create_aws_auth() -> object:
        """Mock create_aws_auth function that returns a dummy AWS auth object."""
        return object()

    def mock_create_opensearch_client(aws_auth: object) -> MockOpenSearchClient:
        """Mock create_opensearch_client function that returns a MockOpenSearchClient."""
        return mock_client

    def mock_require_env(name: str) -> str:
        """Mock require_env function that returns the INDEX_NAME for the INDEX_NAME variable."""
        if name == "INDEX_NAME":
            return INDEX_NAME
        raise ValueError(f"Unexpected env var requested: {name}")

    monkeypatch.setattr(lambda_function.lambda_handler, "create_aws_auth", mock_create_aws_auth)
    monkeypatch.setattr(
        lambda_function.lambda_handler,
        "create_opensearch_client",
        mock_create_opensearch_client,
    )
    monkeypatch.setattr(lambda_function.lambda_handler, "require_env", mock_require_env)
    return mock_client


class TestHandler:
    def test_handler_success(self, monkeypatch):
        """Test handler creates the index when it does not exist and returns expected response."""
        patch_lambda_handler(monkeypatch, "knn_vector")

        resp = lambda_function.handler({}, {})

        assert resp["statusCode"] == 200  # noqa: PLR2004
        assert resp["index_exists"] is True
        assert resp["index_recreated"] is False
        assert resp["index_settings"] == {INDEX_NAME: {"settings": {"index": {"knn": "true"}}}}
        assert resp["index_mappings"] == {
            INDEX_NAME: {
                "mappings": {
                    "properties": {"description_vector": {"type": "knn_vector"}},
                }
            }
        }

    def test_handler_recreates_index_when_vector_mapping_incorrect(self, monkeypatch):
        """Test handler recreates the index when description_vector mapping is not knn_vector."""
        patch_lambda_handler(monkeypatch, "keyword")

        resp = lambda_function.handler({}, {})

        assert resp["statusCode"] == 200  # noqa: PLR2004
        assert resp["index_exists"] is True
        assert resp["index_recreated"] is True
        assert resp["index_settings"] == {INDEX_NAME: {"settings": {"index": {"knn": "true"}}}}
        assert resp["index_mappings"] == {
            INDEX_NAME: {
                "mappings": {
                    "properties": {"description_vector": {"type": "keyword"}},
                }
            }
        }

    def test_handler_clear_index_deletes_and_recreates(self, monkeypatch):
        """Test clear_index action deletes existing index and recreates it."""
        mock_client = patch_lambda_handler(
            monkeypatch, "knn_vector", initially_exists=True
        )

        resp = lambda_function.handler({"action": "clear_index"}, {})

        assert resp["statusCode"] == 200  # noqa: PLR2004
        assert resp["action"] == "clear_index"
        assert resp["index_deleted"] is True
        assert resp["index_recreated"] is True
        assert mock_client.indices.delete_calls == [INDEX_NAME]
        assert mock_client.indices.create_calls == [INDEX_NAME]

    def test_handler_clear_index_when_no_existing_index(self, monkeypatch):
        """Test clear_index action when the index doesn't exist yet."""
        mock_client = patch_lambda_handler(monkeypatch, "knn_vector")

        resp = lambda_function.handler({"action": "clear_index"}, {})

        assert resp["statusCode"] == 200  # noqa: PLR2004
        assert resp["action"] == "clear_index"
        assert resp["index_deleted"] is False
        assert resp["index_recreated"] is True
        assert mock_client.indices.delete_calls == []
        assert mock_client.indices.create_calls == [INDEX_NAME]
