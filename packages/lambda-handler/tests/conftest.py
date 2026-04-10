import json
import logging

import boto3
import moto
import pytest

from utils import get_env_var

AWS_ACCESS_KEY_ID = get_env_var("AWS_ACCESS_KEY_ID")
AWS_REGION = get_env_var("AWS_REGION")
AWS_SECRET_ACCESS_KEY = get_env_var("AWS_SECRET_ACCESS_KEY")
S3_BUCKET = get_env_var("S3_BUCKET")


@pytest.fixture(scope="function")
def moto_setup(monkeypatch: pytest.MonkeyPatch) -> boto3.client:
    """Setup test AWS."""
    with moto.mock_aws():
        monkeypatch.setenv("AWS_ACCESS_KEY_ID", AWS_ACCESS_KEY_ID)
        monkeypatch.setenv("AWS_REGION", AWS_REGION)
        monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", AWS_SECRET_ACCESS_KEY)
        monkeypatch.setenv("OPENSEARCH_ENDPOINT_URL", "https://test-opensearch-endpoint.com")

        # Create the fake S3 bucket
        s3 = boto3.client(
            "s3",
            region_name=AWS_REGION,
            aws_access_key_id=AWS_ACCESS_KEY_ID,
            aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
        )
        s3.create_bucket(Bucket=S3_BUCKET)

        # Add convenience attribute for tests
        s3.bucket_name = S3_BUCKET

        yield s3


@pytest.fixture
def example_s3_event_payload() -> dict:
    """Inner S3 event payload (what SQS body contains as JSON string).

    This example content comes from APHL
    """
    return {
        "version": "0",
        "id": "12345678-1234-5678-9012-123456789012",
        "detail-type": "Object Created",
        "source": "aws.s3",
        "account": "111122223333",
        "time": "2025-09-03T12:34:56Z",
        "region": "us-east-1",
        "resources": ["arn:aws:s3:::my-bucket-name"],
        "detail": {
            "version": "0",
            "bucket": {"name": "ecr-bucket"},
            "object": {
                "key": "TextToCodeSubmission/2025/09/03/1-5f84c7a5-91d7f5c6a2b7c9e08f0d1234",
                "size": 1024,
                "etag": "0123456789abcdef0123456789abcdef",
                "sequencer": "0055AED6DCD90281E5",
            },
            "request-id": "C3D13FE58DE4C810",
            "requester": "arn:aws:iam::111122223333:user/example-user",
            "reason": "PutObject",
        },
    }


@pytest.fixture
def example_sqs_event(example_s3_event_payload: dict) -> dict:
    """Full SQS event that mimics real Lambda input."""
    return {
        "Records": [
            {
                "messageId": "f9ccdff5-0acb-4933-8995-bd7f0ab5f2f7",
                "receiptHandle": "test-receipt-handle",
                "body": json.dumps(example_s3_event_payload),
                "attributes": {
                    "ApproximateReceiveCount": "1",
                    "SentTimestamp": "1752691260451",
                    "SenderId": "AIDAJXNJGGKNS7OSV23OI",
                    "ApproximateFirstReceiveTimestamp": "1752691260458",
                },
                "messageAttributes": {},
                "md5OfBody": "dummy-md5",
                "eventSource": "aws:sqs",
                "eventSourceARN": "arn:aws:sqs:us-east-1:123456789012:queue-name",
                "awsRegion": "us-east-1",
            }
        ]
    }


@pytest.fixture
def caplog_warning(caplog: pytest.LogCaptureFixture) -> logging.Logger:
    """Capture log warnings for tests.

    :param caplog: Pytest fixture for capturing log output
    :return: Caplog instance with warning level set
    """
    caplog.set_level(logging.WARNING)
    return caplog
