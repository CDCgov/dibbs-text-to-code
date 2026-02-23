import io

from text_to_code_lambda import s3_handler


class TestCreateS3Client:
    def test_create_s3_client(self, moto_setup):
        """Test create S3 client."""
        s3_client = s3_handler.create_s3_client()
        assert s3_client.meta.endpoint_url == "https://s3.amazonaws.com"
        assert s3_client.meta.region_name == "us-east-1"
        assert s3_client._get_credentials().secret_key == "test_secret_access_key"
        assert s3_client._get_credentials().access_key == "test_access_key_id"


class TestGetFileContentFromS3Event:
    def test_get_file_content_from_s3_event(self, moto_setup):
        """Test get file content from S3 event."""
        moto_setup.put_object(
            Bucket=moto_setup.bucket_name, Key="test.txt", Body=b"This eICR has errors"
        )

        event = {
            "detail": {"bucket": {"name": moto_setup.bucket_name}, "object": {"key": "test.txt"}}
        }

        content = s3_handler.get_file_content_from_s3_event(event)
        assert content == b"This eICR has errors"


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
        assert credentials.secret_key == "test_secret_access_key"
        assert credentials.token is None


    def test_get_s3_credentials_with_token(self, monkeypatch):
        """Test get S3 credentials with token."""
        monkeypatch.setenv("AWS_ACCESS_KEY_ID", "test2")
        monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "test2")
        monkeypatch.setenv("AWS_SESSION_TOKEN", "test-token")

        credentials = s3_handler.get_s3_credentials()
        assert credentials.access_key == "test2"
        assert credentials.secret_key == "test2"
        assert credentials.token == "test-token"
    
class TestCreateAWSAuth:
    def test_create_aws_auth(self, moto_setup):
        """Test create AWS auth."""
        auth = s3_handler.create_aws_auth()

        assert auth.access_id == "test_access_key_id"
        assert auth.region == "us-east-1"