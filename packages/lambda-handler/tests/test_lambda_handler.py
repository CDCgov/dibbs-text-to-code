import io
import json
from typing import cast
from unittest.mock import Mock

import pytest
from aws_lambda_typing import events as lambda_events

import lambda_handler


class TestCreateS3Client:
    def test_create_s3_client(self, mock_aws_setup):
        """Test create S3 client."""
        s3_client = lambda_handler.create_s3_client()
        assert s3_client.meta.endpoint_url == "https://s3.amazonaws.com"
        assert s3_client.meta.region_name == "us-east-1"
        assert s3_client._get_credentials().secret_key == "test_secret_access_key"  # noqa: S105
        assert s3_client._get_credentials().access_key == "test_access_key_id"


class TestGetEventBridgeDataFromS3Event:
    def test_get_eventbridge_data_from_s3_event(self, mock_aws_setup):
        """Test get file content from S3 event."""
        mock_aws_setup.put_object(
            Bucket=mock_aws_setup.bucket_name, Key="test.txt", Body=b"This eICR has errors"
        )

        event = cast(
            lambda_events.EventBridgeEvent,
            {
                "detail": {
                    "bucket": {"name": mock_aws_setup.bucket_name},
                    "object": {"key": "test.txt"},
                }
            },
        )

        content = lambda_handler.get_eventbridge_data_from_s3_event(event)
        assert content == {"bucket_name": mock_aws_setup.bucket_name, "object_key": "test.txt"}

    def test_get_eventbridge_data_missing_bucket(self):
        """Test that a missing bucket name returns None instead of raising."""
        event = cast(
            lambda_events.EventBridgeEvent,
            {"detail": {"object": {"key": "test.txt"}}},
        )

        result = lambda_handler.get_eventbridge_data_from_s3_event(event)
        assert result == {"bucket_name": None, "object_key": "test.txt"}


class TestGetFileContentFromS3:
    def test_get_file_content_from_s3(self, mock_aws_setup):
        """Test get file content from S3."""
        mock_aws_setup.put_object(
            Bucket=mock_aws_setup.bucket_name, Key="test.txt", Body=b"This eICR has errors"
        )

        content = lambda_handler.get_file_content_from_s3(mock_aws_setup.bucket_name, "test.txt")
        assert content == "This eICR has errors"

    def test_get_file_content_from_s3_nonexistent_object(self, mock_aws_setup):
        """Test get file content from S3 with nonexistent object."""
        with pytest.raises(FileNotFoundError) as e:
            lambda_handler.get_file_content_from_s3(mock_aws_setup.bucket_name, "nonexistent.txt")
        assert str(e.value) == f"S3 object not found: {mock_aws_setup.bucket_name}/nonexistent.txt"


class TestPutFile:
    def test_put_file(self, mock_aws_setup):
        """Test put file."""
        fobj = io.BytesIO(b"This eICR is good")
        lambda_handler.put_file(fobj, mock_aws_setup.bucket_name, "test.txt")

        response = mock_aws_setup.get_object(Bucket=mock_aws_setup.bucket_name, Key="test.txt")
        assert response["Body"].read() == b"This eICR is good"


class TestStripProtocol:
    def test_strip_protocol(self):
        """Test strip protocol."""
        assert (
            lambda_handler.strip_protocol("https://test-endpoint-url.com")
            == "test-endpoint-url.com"
        )
        assert (
            lambda_handler.strip_protocol("http://test-endpoint-url.com") == "test-endpoint-url.com"
        )
        assert lambda_handler.strip_protocol("test-endpoint-url.com") == "test-endpoint-url.com"


class TestGetS3Credentials:
    def test_get_s3_credentials(self, mock_aws_setup):
        """Test get S3 credentials set in conftest.py."""
        credentials = lambda_handler.get_s3_credentials()
        assert credentials.access_key == "test_access_key_id"
        assert credentials.secret_key == "test_secret_access_key"  # noqa: S105
        assert credentials.token is None

    def test_get_s3_credentials_with_token(self, monkeypatch):
        """Test get S3 credentials with token."""
        monkeypatch.setenv("AWS_ACCESS_KEY_ID", "test2")
        monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "test2")
        monkeypatch.setenv("AWS_SESSION_TOKEN", "test-token")

        credentials = lambda_handler.get_s3_credentials()
        assert credentials.access_key == "test2"
        assert credentials.secret_key == "test2"  # noqa: S105
        assert credentials.token == "test-token"  # noqa: S105


class TestCreateAWSAuth:
    def test_create_aws_auth(self, mock_aws_setup):
        """Test create AWS auth."""
        auth = lambda_handler.create_aws_auth()

        assert auth.access_id == "test_access_key_id"
        assert auth.region == "us-east-1"


class TestCheckS3ObjectExists:
    def test_check_s3_object_exists(self, mock_aws_setup):
        """Test check S3 object exists."""
        lambda_handler.put_file(io.BytesIO(b"test content"), mock_aws_setup.bucket_name, "test.txt")

        exists = lambda_handler.check_s3_object_exists(
            mock_aws_setup, mock_aws_setup.bucket_name, "test.txt"
        )
        assert exists

    def test_check_s3_object_does_not_exist(self, mock_aws_setup):
        """Test check S3 object does not exist."""
        exists = lambda_handler.check_s3_object_exists(
            mock_aws_setup, mock_aws_setup.bucket_name, "nonexistent.txt"
        )
        assert not exists

    def test_check_s3_object_exists_unexpected_error(self, mock_aws_setup):
        """Test check S3 object exists with unexpected error."""
        with pytest.raises(Exception, match="Unexpected error while fetching file from S3") as e:
            lambda_handler.check_s3_object_exists(mock_aws_setup, "nonexistent-bucket", "test.txt")
        assert "The specified bucket does not exist" in str(e.value)


class TestCreateOpenSearchClient:
    def test_create_opensearch_client(self, mock_aws_setup):
        """Test create OpenSearch client."""
        expected_port = 443  # The expected default port for the OpenSearch client.
        client = lambda_handler.create_opensearch_client()

        assert client.transport.hosts[0]["host"] == "test-opensearch-endpoint.com"
        assert client.transport.hosts[0]["port"] == expected_port


class TestGetPersistenceId:
    def test_get_persistence_id(self):
        """Test get persistence id."""
        object_key = "TextToCodeSubmission/2025/09/03/1-5f84c7a5-91d7f5c6a2b7c9e08f0d1234"
        persistence_id = lambda_handler.get_persistence_id(object_key, "TextToCodeSubmission")

        assert persistence_id == object_key.split("TextToCodeSubmission")[1]

    def test_get_persistence_id_incorrect_prefix(self):
        """Test get persistence id with incorrect prefix."""
        object_key = "IncorrectPrefix/2025/09/03/1-5f84c7a5-91d7f5c6a2b7c9e08f0d1234"
        with pytest.raises(ValueError, match="does not start with expected prefix"):
            lambda_handler.get_persistence_id(object_key, "TextToCodeSubmission")


class TestRetrieveOpenSearchResults:
    def test_retrieve_opensearch_results(self, snapshot):
        query = {"query": {"match_all": {}}}
        index = "loinc-index"
        opensearch_client = Mock()
        opensearch_client.search.return_value = {
            "took": 4,
            "timed_out": False,
            "_shards": {
                "total": 1,
                "successful": 1,
                "skipped": 0,
                "failed": 0,
            },
            "hits": {
                "total": {
                    "value": 1,
                    "relation": "eq",
                },
                "hits": [
                    {
                        "_index": "loinc-index",
                        "_id": "12345-6",
                        "_score": 1.0,
                        "_source": {
                            "id": 12345,
                            "loinc_code": "12345-6",
                            "loinc_name_type": "Component",
                            "description": "Test LOINC description",
                            "loinc_type": "Laboratory",
                        },
                    }
                ],
            },
        }

        result = lambda_handler.retrieve_opensearch_results(query, index, opensearch_client)

        opensearch_client.search.assert_called_once_with(
            index=index,
            body=query,
        )
        snapshot.assert_match(
            json.dumps(result.model_dump(), indent=2, sort_keys=True),
            "retrieve_opensearch_results.json",
        )
