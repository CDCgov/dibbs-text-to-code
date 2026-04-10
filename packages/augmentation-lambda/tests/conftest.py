import json
import logging
import os
from pathlib import Path

import boto3
import moto
import pytest

from shared_models import EICR_INPUT_PREFIX
from shared_models import S3_BUCKET
from shared_models import SCHEMATRON_ERROR_PREFIX
from shared_models import TTC_INPUT_PREFIX
from shared_models import TTC_METADATA_PREFIX
from shared_models import TTC_OUTPUT_PREFIX

AWS_REGION = "us-east-1"
AWS_ACCESS_KEY_ID = "test_access_key_id"
AWS_SECRET_ACCESS_KEY = "test_secret_access_key"  # noqa: S105
OPENSEARCH_ENDPOINT_URL = "https://test-opensearch-endpoint.com"
TEST_PERSISTENCE_ID = "2025/09/03/1-5f84c7a5-91d7f5c6a2b7c9e08f0d1234"


def pytest_configure() -> None:
    """Configure env variables for pytest."""
    os.environ["S3_BUCKET"] = S3_BUCKET
    os.environ["EICR_INPUT_PREFIX"] = EICR_INPUT_PREFIX
    os.environ["SCHEMATRON_ERROR_PREFIX"] = SCHEMATRON_ERROR_PREFIX
    os.environ["TTC_INPUT_PREFIX"] = TTC_INPUT_PREFIX
    os.environ["TTC_OUTPUT_PREFIX"] = TTC_OUTPUT_PREFIX
    os.environ["TTC_METADATA_PREFIX"] = TTC_METADATA_PREFIX
    os.environ["AWS_REGION"] = AWS_REGION
    os.environ["AWS_ACCESS_KEY_ID"] = AWS_ACCESS_KEY_ID
    os.environ["AWS_SECRET_ACCESS_KEY"] = AWS_SECRET_ACCESS_KEY
    os.environ["OPENSEARCH_ENDPOINT_URL"] = OPENSEARCH_ENDPOINT_URL


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
        "resources": [f"arn:aws:s3:::{S3_BUCKET}"],
        "detail": {
            "version": "0",
            "bucket": {"name": S3_BUCKET},
            "object": {
                "key": f"{TTC_OUTPUT_PREFIX}{TEST_PERSISTENCE_ID}",
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


@pytest.fixture(scope="function")
def mock_aws_setup(monkeypatch: pytest.MonkeyPatch) -> boto3.client:
    """Setup test AWS environment."""
    with moto.mock_aws():
        monkeypatch.setenv("AWS_REGION", AWS_REGION)
        monkeypatch.setenv("AWS_ACCESS_KEY_ID", AWS_ACCESS_KEY_ID)
        monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", AWS_SECRET_ACCESS_KEY)
        monkeypatch.setenv("OPENSEARCH_ENDPOINT_URL", OPENSEARCH_ENDPOINT_URL)
        # Create the single S3 bucket
        s3 = boto3.client(
            "s3",
            region_name=AWS_REGION,
            aws_access_key_id=AWS_ACCESS_KEY_ID,
            aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
        )
        s3.create_bucket(Bucket=S3_BUCKET)

        # Add convenience attributes for tests
        s3.bucket_name = S3_BUCKET
        s3.persistence_id = TEST_PERSISTENCE_ID

        # Put TTC Output file in the mock S3 bucket
        schematron_path = Path("packages/augmentation-lambda/tests/assets/test_ttc_output.json")
        with schematron_path.open() as f:
            schematron_output = f.read()
        s3.put_object(
            Bucket=S3_BUCKET,
            Key=f"{TTC_OUTPUT_PREFIX}{TEST_PERSISTENCE_ID}",
            Body=schematron_output,
        )

        # Put test eCR message file in the mock S3 bucket
        ecr_path = Path("packages/augmentation-lambda/tests/assets/test_eicr.xml")
        with ecr_path.open() as f:
            ecr_message = f.read()
        s3.put_object(
            Bucket=S3_BUCKET,
            Key=f"{EICR_INPUT_PREFIX}{TEST_PERSISTENCE_ID}",
            Body=ecr_message,
        )

        yield s3
