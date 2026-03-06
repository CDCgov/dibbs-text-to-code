import io

import pytest
import s3_handler


class TestCreateS3Client:
    def test_create_s3_client(self, moto_setup):
        """Test create S3 client."""
        s3_client = s3_handler.create_s3_client()
        assert s3_client.meta.endpoint_url == "https://s3.amazonaws.com"
        assert s3_client.meta.region_name == "us-east-1"
        assert s3_client._get_credentials().secret_key == "test_secret_access_key"  # noqa: S105
        assert s3_client._get_credentials().access_key == "test_access_key_id"


class TestGetEventBridgeDataFromS3Event:
    def test_get_eventbridge_data_from_s3_event(self, moto_setup):
        """Test get file content from S3 event."""
        moto_setup.put_object(
            Bucket=moto_setup.bucket_name, Key="test.txt", Body=b"This eICR has errors"
        )

        event = {
            "detail": {"bucket": {"name": moto_setup.bucket_name}, "object": {"key": "test.txt"}}
        }

        content = s3_handler.get_eventbridge_data_from_s3_event(event)
        assert content == {"bucket_name": moto_setup.bucket_name, "object_key": "test.txt"}


class TestGetFileContentFromS3:
    def test_get_file_content_from_s3(self, moto_setup):
        """Test get file content from S3."""
        moto_setup.put_object(
            Bucket=moto_setup.bucket_name, Key="test.txt", Body=b"This eICR has errors"
        )

        content = s3_handler.get_file_content_from_s3(moto_setup.bucket_name, "test.txt")
        assert content == "This eICR has errors"

    def test_get_file_content_from_s3_nonexistent_object(self, moto_setup):
        """Test get file content from S3 with nonexistent object."""
        with pytest.raises(FileNotFoundError) as e:
            s3_handler.get_file_content_from_s3(moto_setup.bucket_name, "nonexistent.txt")
        assert str(e.value) == f"S3 object not found: {moto_setup.bucket_name}/nonexistent.txt"


class TestPutFile:
    def test_put_file(self, moto_setup):
        """Test put file."""
        fobj = io.BytesIO(b"This eICR is good")
        s3_handler.put_file(fobj, moto_setup.bucket_name, "test.txt")

        response = moto_setup.get_object(Bucket=moto_setup.bucket_name, Key="test.txt")
        assert response["Body"].read() == b"This eICR is good"


class TestStripProtocol:
    def test_strip_protocol(self):
        """Test strip protocol."""
        assert s3_handler.strip_protocol("https://test-endpoint-url.com") == "test-endpoint-url.com"
        assert s3_handler.strip_protocol("http://test-endpoint-url.com") == "test-endpoint-url.com"
        assert s3_handler.strip_protocol("test-endpoint-url.com") == "test-endpoint-url.com"


class TestGetS3Credentials:
    def test_get_s3_credentials(self, moto_setup):
        """Test get S3 credentials set in conftest.py."""
        credentials = s3_handler.get_s3_credentials()
        assert credentials.access_key == "test_access_key_id"
        assert credentials.secret_key == "test_secret_access_key"  # noqa: S105
        assert credentials.token is None

    def test_get_s3_credentials_with_token(self, monkeypatch):
        """Test get S3 credentials with token."""
        monkeypatch.setenv("AWS_ACCESS_KEY_ID", "test2")
        monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "test2")
        monkeypatch.setenv("AWS_SESSION_TOKEN", "test-token")

        credentials = s3_handler.get_s3_credentials()
        assert credentials.access_key == "test2"
        assert credentials.secret_key == "test2"  # noqa: S105
        assert credentials.token == "test-token"  # noqa: S105


class TestCreateAWSAuth:
    def test_create_aws_auth(self, moto_setup):
        """Test create AWS auth."""
        auth = s3_handler.create_aws_auth()

        assert auth.access_id == "test_access_key_id"
        assert auth.region == "us-east-1"


class TestCheckS3ObjectExists:
    def test_check_s3_object_exists(self, moto_setup):
        """Test check S3 object exists."""
        s3_handler.put_file(io.BytesIO(b"test content"), moto_setup.bucket_name, "test.txt")

        exists = s3_handler.check_s3_object_exists(moto_setup, moto_setup.bucket_name, "test.txt")
        assert exists

    def test_check_s3_object_does_not_exist(self, moto_setup):
        """Test check S3 object does not exist."""
        exists = s3_handler.check_s3_object_exists(
            moto_setup, moto_setup.bucket_name, "nonexistent.txt"
        )
        assert not exists

    def test_check_s3_object_exists_unexpected_error(self, moto_setup):
        """Test check S3 object exists with unexpected error."""
        with pytest.raises(Exception, match="Unexpected error while fetching file from S3") as e:
            s3_handler.check_s3_object_exists(moto_setup, "nonexistent-bucket", "test.txt")
        assert "The specified bucket does not exist" in str(e.value)


class TestCreateOpenSearchClient:
    def test_create_opensearch_client(self, moto_setup):
        """Test create OpenSearch client."""
        expected_port = 443  # The expected default port for the OpenSearch client.
        auth = s3_handler.create_aws_auth()
        client = s3_handler.create_opensearch_client(auth)

        assert client.transport.hosts[0]["host"] == "test-opensearch-endpoint.com"
        assert client.transport.hosts[0]["port"] == expected_port


class TestRequireEnv:
    def test_require_env(self, monkeypatch):
        """Test require env."""
        monkeypatch.setenv("TEST_ENV_VAR", "test_value")
        value = s3_handler.require_env("TEST_ENV_VAR")
        assert value == "test_value"

    def test_require_env_not_set(self, monkeypatch):
        """Test require env not set."""
        with pytest.raises(
            ValueError,
            match=r"NONEXISTENT_ENV_VAR not set as an environment variable\.",
        ):
            s3_handler.require_env("NONEXISTENT_ENV_VAR")


class TestGetPersistenceId:
    def test_get_persistence_id(self):
        """Test get persistence id."""
        object_key = "TextToCodeSubmission/2025/09/03/1-5f84c7a5-91d7f5c6a2b7c9e08f0d1234"
        persistence_id = s3_handler.get_persistence_id(object_key, "TextToCodeSubmission")

        assert persistence_id == object_key.split("TextToCodeSubmission")[1]

    def test_get_persistence_id_incorrect_prefix(self):
        """Test get persistence id with incorrect prefix."""
        object_key = "IncorrectPrefix/2025/09/03/1-5f84c7a5-91d7f5c6a2b7c9e08f0d1234"
        with pytest.raises(ValueError, match="does not start with expected prefix"):
            s3_handler.get_persistence_id(object_key, "TextToCodeSubmission")
