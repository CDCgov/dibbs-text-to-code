import json
import os
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import boto3
import pytest
import time_machine
from botocore.exceptions import ClientError
from lxml import etree
from moto import mock_aws
from pytest_snapshot.plugin import Snapshot

from augmentation_lambda.lambda_function import handler as augmentation_lambda
from text_to_code_lambda.lambda_function import handler as ttc_handler
from validation import validate_eicr

AUGMENTATION_METADATA_PREFIX = os.environ["AUGMENTATION_METADATA_PREFIX"]
AUGMENTED_EICR_PREFIX = os.environ["AUGMENTED_EICR_PREFIX"]
AWS_ACCESS_KEY_ID = os.environ["AWS_ACCESS_KEY_ID"]
AWS_SECRET_ACCESS_KEY = os.environ["AWS_SECRET_ACCESS_KEY"]
EICR_INPUT_PREFIX = os.environ["EICR_INPUT_PREFIX"]
REGION = os.environ["AWS_REGION"]
S3_BUCKET = os.environ["S3_BUCKET"]
SCHEMATRON_ERROR_PREFIX = os.environ["SCHEMATRON_ERROR_PREFIX"]
TTC_INPUT_PREFIX = os.environ["TTC_INPUT_PREFIX"]
TTC_OUTPUT_PREFIX = os.environ["TTC_OUTPUT_PREFIX"]

ACCOUNT_ID = "123456789012"

QUEUE_1_NAME = "stage1-queue"
QUEUE_2_NAME = "stage2-queue"
RULE_1_NAME = "input-prefix-rule"
RULE_2_NAME = "results-prefix-rule"
FUNCTION_1_NAME = "stage1-processor"
FUNCTION_2_NAME = "stage2-processor"

TEST_PERSISTENCE_ID = os.environ["TEST_PERSISTENCE_ID"]

BASE_FOLDER = Path(__file__).parent
ASSETS_FOLDER = BASE_FOLDER / "assets"

EICR_CASES: tuple[tuple[str, Path, Path], ...] = (
    (
        "eicr_test",
        ASSETS_FOLDER / "eicr_test" / "eicr_test.xml",
        ASSETS_FOLDER / "eicr_test" / "eicr_test_schematron_errors.xml",
    ),
    (
        "eicr_covid",
        ASSETS_FOLDER / "eicr_covid" / "eicr_covid.xml",
        ASSETS_FOLDER / "eicr_covid" / "eicr_covid_schematron_errors.xml",
    ),
)
FAIL_EICR_CASES: tuple[tuple[str, Path, Path], ...] = (
    (
        "eicr_empty",
        ASSETS_FOLDER / "eicr_empty" / "eicr_empty.xml",
        ASSETS_FOLDER / "eicr_empty" / "eicr_empty_schematron_errors.xml",
    ),
)

NAMESPACE_PRESERVATION_SCHEMATRON_PATH = (
    ASSETS_FOLDER / "namespace_preservation" / "namespace_preservation_schematron_errors.xml"
)
NAMESPACE_PRESERVATION_EICR_PATH = (
    ASSETS_FOLDER / "namespace_preservation" / "namespace_preservation_eicr.xml"
)

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
    def _run_eicr_pipeline(
        self,
        aws,
        infra,
        schematron_path: str,
        eicr_path: str,
        mock_lambda_context,
    ) -> None:
        # Upload Schematron errors to S3
        with open(
            Path(schematron_path),
            "rb",
        ) as schematron_errors_file:
            aws["s3"].upload_fileobj(
                schematron_errors_file,
                S3_BUCKET,
                f"{SCHEMATRON_ERROR_PREFIX}{TEST_PERSISTENCE_ID}",
            )

        # Upload eICR to S3
        with open(
            Path(eicr_path),
            "rb",
        ) as schematron_errors_file:
            aws["s3"].upload_fileobj(
                schematron_errors_file,
                S3_BUCKET,
                f"{EICR_INPUT_PREFIX}{TEST_PERSISTENCE_ID}",
            )
        # Upload message to S3
        with open(
            Path(eicr_path),
            "rb",
        ) as schematron_errors_file:
            aws["s3"].upload_fileobj(
                schematron_errors_file,
                S3_BUCKET,
                f"{TTC_INPUT_PREFIX}{TEST_PERSISTENCE_ID}",
            )

        # Read the auto-generated SQS message
        q1 = _drain_sqs_for_prefix(aws["sqs"], infra["queue1_url"], TTC_INPUT_PREFIX)

        assert q1 != []

        # Feed it to the handler as Lambda would receive it
        sqs_event = _build_sqs_event([json.loads(q1[0]["Body"])], QUEUE_1_NAME)

        _ = ttc_handler(sqs_event, mock_lambda_context)

        q2 = _drain_sqs_for_prefix(aws["sqs"], infra["queue2_url"], TTC_OUTPUT_PREFIX)

        if q2 == []:
            return

        sqs_event = _build_sqs_event([json.loads(q2[0]["Body"])], QUEUE_2_NAME)

        with time_machine.travel(
            datetime(2026, 2, 13, 15, 27, 57, tzinfo=ZoneInfo("America/New_York")), tick=False
        ):
            _ = augmentation_lambda(sqs_event, mock_lambda_context)

    def _read_s3_object(self, aws, key: str) -> str:
        return aws["s3"].get_object(Bucket=S3_BUCKET, Key=key)["Body"].read().decode("utf-8")

    def _assert_s3_object_not_found(self, aws, key: str, eicr_id: str) -> None:
        with pytest.raises(ClientError) as exc_info:
            aws["s3"].get_object(Bucket=S3_BUCKET, Key=key)

        assert exc_info.value.response["Error"]["Code"] == "NoSuchKey", eicr_id

    @pytest.mark.parametrize(
        ("eicr_id", "eicr_path", "schematron_path"),
        EICR_CASES,
        ids=[eicr_case[0] for eicr_case in EICR_CASES],
    )
    def test_upload_and_process(
        self,
        eicr_id: str,
        eicr_path: str,
        schematron_path: str,
        aws,
        infra,
        snapshot: Snapshot,
        mock_opensearch,
        mock_lambda_context,
    ):
        self._run_eicr_pipeline(
            aws,
            infra,
            schematron_path,
            eicr_path,
            mock_lambda_context,
        )

        augmented_eicr = self._read_s3_object(
            aws,
            f"{AUGMENTED_EICR_PREFIX}{TEST_PERSISTENCE_ID}",
        )
        snapshot.assert_match(augmented_eicr, f"{eicr_id}_augmented_eicr.xml")

        # Validate augmented eICR
        actual_validation_results = validate_eicr(augmented_eicr)
        assert actual_validation_results == []  # Empty list means no errors.

        augmentation_metadata = json.dumps(
            json.loads(
                self._read_s3_object(
                    aws,
                    f"{AUGMENTATION_METADATA_PREFIX}{TEST_PERSISTENCE_ID}"
                ),
            indent=2,
            sort_keys=True,
        )

        snapshot.assert_match(augmentation_metadata, f"{eicr_id}_augmentation_metadata.json")

    @pytest.mark.parametrize(
        ("eicr_id", "eicr_path", "schematron_path"),
        FAIL_EICR_CASES,
        ids=[eicr_case[0] for eicr_case in FAIL_EICR_CASES],
    )
    def test_upload_and_process_failure_cases(
        self,
        eicr_id: str,
        eicr_path: str,
        schematron_path: str,
        aws,
        infra,
        mock_opensearch,
        mock_lambda_context,
    ):
        self._run_eicr_pipeline(
            aws,
            infra,
            schematron_path,
            eicr_path,
            mock_lambda_context,
        )

        self._assert_s3_object_not_found(
            aws,
            f"{TTC_OUTPUT_PREFIX}{TEST_PERSISTENCE_ID}",
            eicr_id,
        )
        self._assert_s3_object_not_found(
            aws,
            f"{AUGMENTED_EICR_PREFIX}{TEST_PERSISTENCE_ID}",
            eicr_id,
        )
        self._assert_s3_object_not_found(
            aws,
            f"{AUGMENTATION_METADATA_PREFIX}{TEST_PERSISTENCE_ID}",
            eicr_id,
        )


@pytest.mark.e2e
class TestNamespacePreservation:
    """Regression test for the APHL-reported RCKMS 422 rejection.

    The augmenter previously stripped CDA namespaces during parsing and never put
    them back on serialization, producing output that RCKMS rejected as
    'Payload is missing or empty'. The test feeds the original eICR Geo used to
    surface the bug through the local pipeline and asserts the augmented output
    declares every namespace the input declared, with the root in the CDA
    namespace.
    """

    def test_augmented_eicr_preserves_cda_namespaces(
        self,
        aws,
        infra,
        mock_opensearch,
        mock_lambda_context,
    ):
        with open(NAMESPACE_PRESERVATION_SCHEMATRON_PATH, "rb") as schematron_file:
            aws["s3"].upload_fileobj(
                schematron_file,
                S3_BUCKET,
                f"{SCHEMATRON_ERROR_PREFIX}{TEST_PERSISTENCE_ID}",
            )
        with open(NAMESPACE_PRESERVATION_EICR_PATH, "rb") as eicr_file:
            aws["s3"].upload_fileobj(
                eicr_file,
                S3_BUCKET,
                f"{EICR_INPUT_PREFIX}{TEST_PERSISTENCE_ID}",
            )
        with open(NAMESPACE_PRESERVATION_EICR_PATH, "rb") as eicr_file:
            aws["s3"].upload_fileobj(
                eicr_file,
                S3_BUCKET,
                f"{TTC_INPUT_PREFIX}{TEST_PERSISTENCE_ID}",
            )

        q1 = _drain_sqs_for_prefix(aws["sqs"], infra["queue1_url"], TTC_INPUT_PREFIX)
        ttc_handler(
            _build_sqs_event([json.loads(q1[0]["Body"])], QUEUE_1_NAME), mock_lambda_context
        )

        q2 = _drain_sqs_for_prefix(aws["sqs"], infra["queue2_url"], TTC_OUTPUT_PREFIX)
        with time_machine.travel(
            datetime(2026, 2, 13, 15, 27, 57, tzinfo=ZoneInfo("America/New_York")), tick=False
        ):
            augmentation_lambda(
                _build_sqs_event([json.loads(q2[0]["Body"])], QUEUE_2_NAME),
                mock_lambda_context,
            )

        augmented_eicr = (
            aws["s3"]
            .get_object(Bucket=S3_BUCKET, Key=f"{AUGMENTED_EICR_PREFIX}{TEST_PERSISTENCE_ID}")[
                "Body"
            ]
            .read()
            .decode("utf-8")
        )

        # Verify that the input had the namespace declarations we expect to see preserved,
        # so that this regression test stays meaningful if the fixture is ever swapped out.
        with open(NAMESPACE_PRESERVATION_EICR_PATH, "rb") as eicr_file:
            input_nsmap = etree.fromstring(eicr_file.read()).nsmap
        assert input_nsmap == {
            None: "urn:hl7-org:v3",
            "cda": "urn:hl7-org:v3",
            "sdtc": "urn:hl7-org:sdtc",
            "voc": "http://www.lantanagroup.com/voc",
            "xsi": "http://www.w3.org/2001/XMLSchema-instance",
        }

        augmented_root = etree.fromstring(augmented_eicr.encode("utf-8"))

        # The default CDA namespace must be declared — without it, RCKMS reads every
        # child element as being in the null namespace and rejects with 422.
        assert augmented_root.nsmap == input_nsmap, (
            "Augmented eICR root namespace declarations diverged from input: "
            f"{dict(augmented_root.nsmap)}"
        )
        assert augmented_root.tag == "{urn:hl7-org:v3}ClinicalDocument"

        # Spot-check a descendant the augmenter touches: every <translation> it injects
        # must resolve under the CDA namespace, not the null namespace.
        translations = augmented_root.xpath(
            "//cda:translation", namespaces={"cda": "urn:hl7-org:v3"}
        )
        assert translations, "Augmenter did not inject any <translation> elements"
        for translation in translations:
            assert etree.QName(translation).namespace == "urn:hl7-org:v3"
