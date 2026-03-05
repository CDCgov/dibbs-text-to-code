import json
import logging
import os
from pathlib import Path

import boto3
import moto
import pytest


@pytest.fixture(scope="function")
def moto_setup(monkeypatch: pytest.MonkeyPatch) -> boto3.client:
    """Setup test AWS."""
    with moto.mock_aws():
        monkeypatch.setenv("AWS_REGION", "us-east-1")
        monkeypatch.setenv("AWS_ACCESS_KEY_ID", "test_access_key_id")
        monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "test_secret_access_key")
        bucket_name = "test-bucket"
        monkeypatch.setenv("OPENSEARCH_ENDPOINT_URL", "https://test-opensearch-endpoint.com")

        # Create the fake S3 bucket
        s3 = boto3.client(
            "s3",
            region_name=os.environ["AWS_REGION"],
            aws_access_key_id=os.environ["AWS_ACCESS_KEY_ID"],
            aws_secret_access_key=os.environ["AWS_SECRET_ACCESS_KEY"],
        )
        s3.create_bucket(Bucket=bucket_name)

        # Add convenience attribute for tests
        s3.bucket_name = bucket_name

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
            "bucket": {"name": "eCRMessageV2"},
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


@pytest.fixture(scope="function")
def full_moto_setup(monkeypatch: pytest.MonkeyPatch) -> boto3.client:
    """Setup test AWS."""
    test_persistance_id = "2025/09/03/1-5f84c7a5-91d7f5c6a2b7c9e08f0d1234"

    with moto.mock_aws():
        monkeypatch.setenv("EICR_INPUT_PREFIX", "eCRMessageV2")
        monkeypatch.setenv("SCHEMATRON_ERROR_PREFIX", "schematronErrors")
        monkeypatch.setenv("TTC_INPUT_PREFIX", "TextToCodeSubmission")
        monkeypatch.setenv("TTC_OUTPUT_PREFIX", "TTCOutput")
        monkeypatch.setenv("TTC_METADATA_PREFIX", "TTCMetadata")
        monkeypatch.setenv("AWS_REGION", "us-east-1")
        monkeypatch.setenv("AWS_ACCESS_KEY_ID", "test_access_key_id")
        monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "test_secret_access_key")
        monkeypatch.setenv("OPENSEARCH_ENDPOINT_URL", "https://test-opensearch-endpoint.com")

        # Create the fake S3 bucket
        s3 = boto3.client(
            "s3",
            region_name=os.environ["AWS_REGION"],
            aws_access_key_id=os.environ["AWS_ACCESS_KEY_ID"],
            aws_secret_access_key=os.environ["AWS_SECRET_ACCESS_KEY"],
        )
        s3.create_bucket(Bucket=os.getenv("EICR_INPUT_PREFIX").split("/")[0])
        s3.create_bucket(Bucket=os.getenv("SCHEMATRON_ERROR_PREFIX").split("/")[0])
        s3.create_bucket(Bucket=os.getenv("TTC_INPUT_PREFIX").split("/")[0])
        s3.create_bucket(Bucket=os.getenv("TTC_OUTPUT_PREFIX").split("/")[0])
        s3.create_bucket(Bucket=os.getenv("TTC_METADATA_PREFIX").split("/")[0])

        # Add convenience attribute for tests
        s3.ecr_bucket_name = os.getenv("EICR_INPUT_PREFIX").split("/")[0]
        s3.schematron_bucket_name = os.getenv("SCHEMATRON_ERROR_PREFIX").split("/")[0]
        s3.ttc_input_bucket_name = os.getenv("TTC_INPUT_PREFIX").split("/")[0]
        s3.ttc_output_bucket_name = os.getenv("TTC_OUTPUT_PREFIX").split("/")[0]
        s3.ttc_metadata_bucket_name = os.getenv("TTC_METADATA_PREFIX").split("/")[0]

        # Put test Schematron error file in the mock S3 bucket
        current_dir = Path(__file__).parent.parent.parent
        schematron_path = (
            current_dir / "text-to-code" / "tests" / "assets" / "test_schematron_errors.xml"
        )
        with schematron_path.open() as f:
            schematron_output = f.read()
        s3.put_object(
            Bucket=s3.schematron_bucket_name,
            Key=f"{test_persistance_id}/test_schematron.xml",
            Body=schematron_output,
        )

        # Put test eCR message file in the mock S3 bucket
        ecr_path = current_dir / "text-to-code" / "tests" / "assets" / "basic_test_eicr.xml"
        with ecr_path.open() as f:
            ecr_message = f.read()
        s3.put_object(
            Bucket=s3.ecr_bucket_name,
            Key=f"{test_persistance_id}",
            Body=ecr_message,
        )

        yield s3
