import json
from datetime import datetime
from pathlib import Path
from uuid import UUID
from zoneinfo import ZoneInfo

import boto3
import pytest
import time_machine
from moto import mock_aws
from pytest_mock import MockerFixture
from pytest_snapshot.plugin import Snapshot

from augmentation_lambda.lambda_function import handler as augmentation_lambda
from text_to_code_lambda.lambda_function import handler as ttc_handler
from utils import get_env_var

AUGMENTATION_METADATA_PREFIX = get_env_var("AUGMENTATION_METADATA_PREFIX")
AUGMENTED_EICR_PREFIX = get_env_var("AUGMENTED_EICR_PREFIX")
AWS_ACCESS_KEY_ID = get_env_var("AWS_ACCESS_KEY_ID")
AWS_SECRET_ACCESS_KEY = get_env_var("AWS_SECRET_ACCESS_KEY")
AWS_ACCESS_KEY_ID = "test_access_key_id"
EICR_INPUT_PREFIX = get_env_var("EICR_INPUT_PREFIX")
REGION = get_env_var("AWS_REGION")
S3_BUCKET = get_env_var("S3_BUCKET")
SCHEMATRON_ERROR_PREFIX = get_env_var("SCHEMATRON_ERROR_PREFIX")
TTC_INPUT_PREFIX = get_env_var("TTC_INPUT_PREFIX")
TTC_OUTPUT_PREFIX = get_env_var("TTC_OUTPUT_PREFIX")

ACCOUNT_ID = "123456789012"

QUEUE_1_NAME = "stage1-queue"
QUEUE_2_NAME = "stage2-queue"
RULE_1_NAME = "input-prefix-rule"
RULE_2_NAME = "results-prefix-rule"
FUNCTION_1_NAME = "stage1-processor"
FUNCTION_2_NAME = "stage2-processor"

TEST_PERSISTENCE_ID = "2025/09/03/1-5f84c7a5-91d7f5c6a2b7c9e08f0d1234"

SCHEMATRON_PATH = "e2e/assets/test_schematron_errors.xml"
EICR_PATH = "e2e/assets/test_eicr.xml"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _create_iam_role(iam_client) -> str:
    role = iam_client.create_role(
        RoleName="lambda-execution-role",
        AssumeRolePolicyDocument=json.dumps(
            {
                "Version": "2012-10-17",
                "Statement": [
                    {
                        "Effect": "Allow",
                        "Principal": {"Service": "lambda.amazonaws.com"},
                        "Action": "sts:AssumeRole",
                    }
                ],
            }
        ),
        Path="/",
    )
    return role["Role"]["Arn"]


def _build_sqs_event(messages: list[dict], queue_name: str) -> dict:
    return {
        "Records": [
            {
                "messageId": f"msg-{i}",
                "receiptHandle": f"handle-{i}",
                "body": json.dumps(msg),
                "attributes": {},
                "messageAttributes": {},
                "md5OfBody": "",
                "eventSource": "aws:sqs",
                "eventSourceARN": f"arn:aws:sqs:{REGION}:{ACCOUNT_ID}:{queue_name}",
                "awsRegion": REGION,
            }
            for i, msg in enumerate(messages)
        ]
    }


def _drain_sqs(sqs_client, queue_url, max_messages=10) -> list[dict]:
    resp = sqs_client.receive_message(
        QueueUrl=queue_url,
        MaxNumberOfMessages=max_messages,
        WaitTimeSeconds=0,
    )
    return resp.get("Messages", [])


def _drain_sqs_for_prefix(sqs_client, queue_url, prefix, max_messages=10) -> list[dict]:
    """Drain a queue but only return messages whose object key starts with prefix."""
    all_msgs = _drain_sqs(sqs_client, queue_url, max_messages)
    return [
        m for m in all_msgs if json.loads(m["Body"])["detail"]["object"]["key"].startswith(prefix)
    ]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def aws(monkeypatch):
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", AWS_ACCESS_KEY_ID)
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", AWS_SECRET_ACCESS_KEY)
    monkeypatch.setenv("AWS_SECURITY_TOKEN", "testing")
    monkeypatch.setenv("AWS_SESSION_TOKEN", "testing")
    monkeypatch.setenv("AWS_DEFAULT_REGION", REGION)

    with mock_aws():
        clients = {
            "s3": boto3.client("s3", region_name=REGION),
            "sqs": boto3.client("sqs", region_name=REGION),
            "events": boto3.client("events", region_name=REGION),
            "iam": boto3.client("iam", region_name=REGION),
        }
        yield clients


@pytest.fixture
def infra(aws):
    s3 = aws["s3"]
    sqs = aws["sqs"]
    events = aws["events"]

    # --- Single bucket with EventBridge enabled ---
    s3.create_bucket(Bucket=S3_BUCKET)
    s3.put_bucket_notification_configuration(
        Bucket=S3_BUCKET,
        NotificationConfiguration={"EventBridgeConfiguration": {}},
    )

    # --- SQS queues ---
    q1_url = sqs.create_queue(QueueName=QUEUE_1_NAME)["QueueUrl"]
    q1_arn = sqs.get_queue_attributes(
        QueueUrl=q1_url,
        AttributeNames=["QueueArn"],
    )["Attributes"]["QueueArn"]

    q2_url = sqs.create_queue(QueueName=QUEUE_2_NAME)["QueueUrl"]
    q2_arn = sqs.get_queue_attributes(
        QueueUrl=q2_url,
        AttributeNames=["QueueArn"],
    )["Attributes"]["QueueArn"]

    # --- EventBridge rule 1: input/ prefix → queue 1 ---
    events.put_rule(
        Name=RULE_1_NAME,
        EventPattern=json.dumps(
            {
                "source": ["aws.s3"],
                "detail-type": ["Object Created"],
                "detail": {
                    "bucket": {"name": [S3_BUCKET]},
                    "object": {"key": [{"prefix": TTC_INPUT_PREFIX}]},
                },
            }
        ),
        State="ENABLED",
    )
    events.put_targets(
        Rule=RULE_1_NAME,
        Targets=[{"Id": "stage1-target", "Arn": q1_arn}],
    )

    # --- EventBridge rule 2: results/ prefix → queue 2 ---
    events.put_rule(
        Name=RULE_2_NAME,
        EventPattern=json.dumps(
            {
                "source": ["aws.s3"],
                "detail-type": ["Object Created"],
                "detail": {
                    "bucket": {"name": [S3_BUCKET]},
                    "object": {"key": [{"prefix": TTC_OUTPUT_PREFIX}]},
                },
            }
        ),
        State="ENABLED",
    )
    events.put_targets(
        Rule=RULE_2_NAME,
        Targets=[{"Id": "stage2-target", "Arn": q2_arn}],
    )

    return {
        "queue1_url": q1_url,
        "queue1_arn": q1_arn,
        "queue2_url": q2_url,
        "queue2_arn": q2_arn,
    }


@pytest.mark.e2e
class TestEndToEndSimulated:
    def test_upload_and_process(
        self, aws, infra, snapshot: Snapshot, mock_opensearch, mocker: MockerFixture
    ):
        # Upload Schematron errors to S3
        with open(
            Path(SCHEMATRON_PATH),
            "rb",
        ) as schematron_errors_file:
            aws["s3"].upload_fileobj(
                schematron_errors_file,
                S3_BUCKET,
                f"{SCHEMATRON_ERROR_PREFIX}{TEST_PERSISTENCE_ID}",
            )

        # Upload eICR to S3
        with open(
            Path(EICR_PATH),
            "rb",
        ) as schematron_errors_file:
            aws["s3"].upload_fileobj(
                schematron_errors_file,
                S3_BUCKET,
                f"{EICR_INPUT_PREFIX}{TEST_PERSISTENCE_ID}",
            )
        # Upload message to S3
        with open(
            Path(EICR_PATH),
            "rb",
        ) as schematron_errors_file:
            aws["s3"].upload_fileobj(
                schematron_errors_file,
                S3_BUCKET,
                f"{TTC_INPUT_PREFIX}{TEST_PERSISTENCE_ID}",
            )

        # Read the auto-generated SQS message
        q1 = _drain_sqs_for_prefix(aws["sqs"], infra["queue1_url"], TTC_INPUT_PREFIX)

        # Feed it to the handler as Lambda would receive it
        sqs_event = _build_sqs_event([json.loads(q1[0]["Body"])], QUEUE_1_NAME)

        _ = ttc_handler(sqs_event, None)

        ##########################################################
        # Augmenter
        doc_id = UUID("12345678-1234-5678-1234-567812345678")
        set_id = UUID("87654321-4321-8765-4321-876543218765")

        mocker.patch("augmentation.services.eicr_augmenter.uuid4", side_effect=[doc_id, set_id])

        q2 = _drain_sqs_for_prefix(aws["sqs"], infra["queue2_url"], TTC_OUTPUT_PREFIX)
        sqs_event = _build_sqs_event([json.loads(q2[0]["Body"])], QUEUE_2_NAME)

        with time_machine.travel(
            datetime(2026, 2, 13, 15, 27, 57, tzinfo=ZoneInfo("America/New_York")), tick=False
        ):
            _ = augmentation_lambda(sqs_event, None)

        augmented_eicr = (
            aws["s3"]
            .get_object(Bucket=S3_BUCKET, Key=f"{AUGMENTED_EICR_PREFIX}{TEST_PERSISTENCE_ID}")[
                "Body"
            ]
            .read()
            .decode("utf-8")
        )
        snapshot.assert_match(augmented_eicr, "augmented_eicr.xml")

        augmentation_metadata = (
            aws["s3"]
            .get_object(
                Bucket=S3_BUCKET, Key=f"{AUGMENTATION_METADATA_PREFIX}{TEST_PERSISTENCE_ID}"
            )["Body"]
            .read()
            .decode("utf-8")
        )

        snapshot.assert_match(augmentation_metadata, "augmentation_metadata.json")
