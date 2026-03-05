from index_lambda import lambda_function


class TestHandler:
    def test_handler_success(self, monkeypatch):
        """Test handler creates the index when it does not exist and returns expected response."""
        index_name = "test-index"

        class MockIndices:
            def __init__(self) -> None:
                self._exists_calls = 0
                self.created = False
                self.deleted = False
                self.last_create_body = None

            def exists(self, index: str) -> bool:
                self._exists_calls += 1
                return self._exists_calls != 1

            def create(self, index: str, body: dict) -> None:
                self.created = True
                self.last_create_body = body

            def delete(self, index: str) -> None:
                self.deleted = True

            def get_settings(self, index: str) -> dict:
                return {index_name: {"settings": {"index": {"knn": "true"}}}}

            def get_mapping(self, index: str) -> dict:
                return {
                    index_name: {
                        "mappings": {
                            "properties": {"description_vector": {"type": "knn_vector"}},
                        }
                    }
                }

        class MockOpenSearchClient:
            def __init__(self) -> None:
                self.indices = MockIndices()

        def mock_create_aws_auth() -> object:
            return object()

        def mock_create_opensearch_client(aws_auth: object) -> MockOpenSearchClient:
            return MockOpenSearchClient()

        def mock_require_env(name: str) -> str:
            if name == "INDEX_NAME":
                return index_name
            raise ValueError(f"Unexpected env var requested: {name}")

        monkeypatch.setattr(lambda_function.s3_handler, "create_aws_auth", mock_create_aws_auth)
        monkeypatch.setattr(
            lambda_function.s3_handler,
            "create_opensearch_client",
            mock_create_opensearch_client,
        )
        monkeypatch.setattr(lambda_function.s3_handler, "require_env", mock_require_env)

        resp = lambda_function.handler({}, {})

        assert resp["statusCode"] == 200  # noqa: PLR2004
        assert resp["index_exists"] is True
        assert resp["index_recreated"] is False
        assert resp["index_settings"] == {index_name: {"settings": {"index": {"knn": "true"}}}}
        assert resp["index_mappings"] == {
            index_name: {
                "mappings": {
                    "properties": {"description_vector": {"type": "knn_vector"}},
                }
            }
        }

    def test_handler_recreates_index_when_vector_mapping_incorrect(self, monkeypatch):
        """Test handler recreates the index when description_vector mapping is not knn_vector."""
        index_name = "test-index"

        class MockIndices:
            def __init__(self) -> None:
                self._exists_calls = 0
                self.created_count = 0
                self.deleted_count = 0
                self.create_bodies = []

            def exists(self, index: str) -> bool:
                self._exists_calls += 1
                return self._exists_calls != 1

            def create(self, index: str, body: dict) -> None:
                self.created_count += 1
                self.create_bodies.append(body)

            def delete(self, index: str) -> None:
                self.deleted_count += 1

            def get_settings(self, index: str) -> dict:
                return {index_name: {"settings": {"index": {"knn": "true"}}}}

            def get_mapping(self, index: str) -> dict:
                return {
                    index_name: {
                        "mappings": {
                            "properties": {"description_vector": {"type": "keyword"}},
                        }
                    }
                }

        class MockOpenSearchClient:
            def __init__(self) -> None:
                self.indices = MockIndices()

        def mock_create_aws_auth() -> object:
            return object()

        def mock_create_opensearch_client(aws_auth: object) -> MockOpenSearchClient:
            return MockOpenSearchClient()

        def mock_require_env(name: str) -> str:
            if name == "INDEX_NAME":
                return index_name
            raise ValueError(f"Unexpected env var requested: {name}")

        monkeypatch.setattr(lambda_function.s3_handler, "create_aws_auth", mock_create_aws_auth)
        monkeypatch.setattr(
            lambda_function.s3_handler,
            "create_opensearch_client",
            mock_create_opensearch_client,
        )
        monkeypatch.setattr(lambda_function.s3_handler, "require_env", mock_require_env)

        resp = lambda_function.handler({}, {})

        assert resp["statusCode"] == 200  # noqa: PLR2004
        assert resp["index_exists"] is True
        assert resp["index_recreated"] is True
        assert resp["index_settings"] == {index_name: {"settings": {"index": {"knn": "true"}}}}
        assert resp["index_mappings"] == {
            index_name: {
                "mappings": {
                    "properties": {"description_vector": {"type": "keyword"}},
                }
            }
        }
