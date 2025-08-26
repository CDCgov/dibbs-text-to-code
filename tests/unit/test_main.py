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
