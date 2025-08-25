import io

from dibbs_text_to_code import s3_handler


class TestCreateS3Client:
    def test_create_s3_client(self, moto_setup):
        s3_client = s3_handler.create_s3_client()
        assert s3_client.meta.endpoint_url == "https://s3.amazonaws.com"
        assert s3_client.meta.region_name == "us-east-1"
        assert s3_client._get_credentials().secret_key == "test"
        assert s3_client._get_credentials().access_key == "test"


class TestGetFileContentFromS3Event:
    def test_get_file_content_from_s3_event(self, moto_setup):
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
        fobj = io.BytesIO(b"This eICR is good")
        s3_handler.put_file(fobj, moto_setup.bucket_name, "test.txt")

        response = moto_setup.get_object(Bucket=moto_setup.bucket_name, Key="test.txt")
        assert response["Body"].read() == b"This eICR is good"
