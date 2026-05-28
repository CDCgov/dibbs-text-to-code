import json
import os
from collections.abc import Iterator
from pathlib import Path

import boto3
import moto
import pytest
from botocore.client import BaseClient

from augmentation_lambda import lambda_function

S3_BUCKET = os.environ["S3_BUCKET"]
AWS_REGION = os.environ["AWS_REGION"]
AWS_ACCESS_KEY_ID = os.environ["AWS_ACCESS_KEY_ID"]
AWS_SECRET_ACCESS_KEY = os.environ["AWS_SECRET_ACCESS_KEY"]
TEST_PERSISTENCE_ID = os.environ["TEST_PERSISTENCE_ID"]

TTC_INPUT_PREFIX = os.environ["TTC_INPUT_PREFIX"]
TTC_OUTPUT_PREFIX = os.environ["TTC_OUTPUT_PREFIX"]
AUGMENTED_EICR_PREFIX = os.environ["AUGMENTED_EICR_PREFIX"]
AUGMENTATION_METADATA_PREFIX = os.environ["AUGMENTATION_METADATA_PREFIX"]

TEST_EICR_PATH = (
    Path(__file__).parent.parent.parent
    / "augmentation"
    / "tests"
    / "assets"
    / "basic_test_eicr.xml"
)


@pytest.fixture
def test_ttc_output() -> dict[str, object]:
    """A test example of the output of the TTC lambda."""
    return {
        "persistence_id": TEST_PERSISTENCE_ID,
        "eicr_metadata": {},
        "schematron_errors": {
            "Lab Test Name Resulted": [
                {
                    "schematron_error": "Text to Code: Lab Test Name Resulted does not have a @code attribute",
                    "schematron_error_xpath": "/ClinicalDocument/component/structuredBody/component/section/entry/component/observation",
                    "field_type": "Lab Test Name Resulted",
                    "new_translation": {
                        "code": "109224-6",
                        "code_system": "2.16.840.1.113883.6.1",
                        "code_system_name": "LOINC",
                        "display_name": "Weed Allergen Mix 3 IgE Ab",
                        "value_set": None,
                        "value_set_version": None,
                        "original_text": "A custom code in original text.",
                    },
                }
            ]
        },
    }


@pytest.fixture
def example_s3_event_payload() -> dict[str, object]:
    """EventBridge S3 event payload (what SQS body contains as JSON string)."""
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


@pytest.fixture(scope="function")
def example_sqs_event(example_s3_event_payload: dict[str, object]) -> dict[str, object]:
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


@pytest.fixture(scope="function")
def mock_aws_setup(
    monkeypatch: pytest.MonkeyPatch, test_ttc_output: dict[str, object]
) -> Iterator[BaseClient]:
    """Setup test AWS environment with moto mock S3."""
    with moto.mock_aws():
        monkeypatch.setenv("AWS_REGION", AWS_REGION)
        monkeypatch.setenv("AWS_ACCESS_KEY_ID", AWS_ACCESS_KEY_ID)
        monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", AWS_SECRET_ACCESS_KEY)

        s3 = boto3.client(
            "s3",
            region_name=AWS_REGION,
            aws_access_key_id=AWS_ACCESS_KEY_ID,
            aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
        )
        s3.create_bucket(Bucket=S3_BUCKET)

        s3.bucket_name = S3_BUCKET
        s3.persistence_id = TEST_PERSISTENCE_ID

        # Put test eICR in mock S3
        with TEST_EICR_PATH.open() as f:
            eicr_content = f.read()
        s3.put_object(
            Bucket=S3_BUCKET,
            Key=f"{TTC_INPUT_PREFIX}{TEST_PERSISTENCE_ID}",
            Body=eicr_content,
        )

        # Put test TTC output in mock S3
        s3.put_object(
            Bucket=S3_BUCKET,
            Key=f"{TTC_OUTPUT_PREFIX}{TEST_PERSISTENCE_ID}",
            Body=json.dumps(test_ttc_output),
        )

        # Reset cached S3 client so Lambda creates a new one inside moto context
        monkeypatch.setattr(lambda_function, "_cached_s3_client", None, raising=False)

        yield s3

        monkeypatch.setattr(lambda_function, "_cached_s3_client", None, raising=False)
