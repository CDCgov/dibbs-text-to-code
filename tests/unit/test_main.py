import json

import pytest

from dibbs_text_to_code import main


class TestHandler:
    def test_handler(self):
        resp = main.handler({}, {})
        assert resp == {"message": "DIBBS Text to Code!", "event": {}, "file_contents": []}

    @pytest.mark.parametrize("num_records", [1, 3])
    def test_handler_reads_multiple_files(self, moto_setup, num_records):
        expected_contents = []

        # Create S3 events
        records = []
        for i in range(num_records):
            key = f"test-{i}.txt"
            content = f"Test file {i}".encode()
            expected_contents.append(content)

            moto_setup.put_object(Bucket=moto_setup.bucket_name, Key=key, Body=content)

            s3_event = {
                "detail": {"bucket": {"name": moto_setup.bucket_name}, "object": {"key": key}}
            }
            records.append({"body": json.dumps(s3_event)})
        # Create event and fake context
        event = {"Records": records}
        context = {}

        result = main.handler(event, context)

        assert result["file_contents"] == expected_contents
        assert len(result["file_contents"]) == num_records

    def test_handler_no_records(self):
        event = {"Records": []}
        context = {}

        result = main.handler(event, context)

        assert result["file_contents"] == []
        assert len(result["file_contents"]) == 0


class TestCreateS3Client:
    def test_create_s3_client(self, moto_setup):
        s3_client = main.create_s3_client()
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

        content = main.get_file_content_from_s3_event(event)
        assert content == b"This eICR has errors"
