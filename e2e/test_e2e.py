import json
import os
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import boto3
import pytest
import time_machine
from lxml import etree
from moto import mock_aws
from pytest_snapshot.plugin import Snapshot

from augmentation.models import Metadata as AugmentationMetadata
from augmentation_lambda.lambda_function import handler as augmentation_lambda
from shared_models import PassthroughReason, TTCAugmenterInput
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

CDA_NAMESPACE = "urn:hl7-org:v3"
CDA_NAMESPACES: dict[str, str] = {"cda": CDA_NAMESPACE}
REGENERATED_DOCUMENT_HEADER_TAGS: tuple[str, str, str, str] = (
    f"{{{CDA_NAMESPACE}}}id",
    f"{{{CDA_NAMESPACE}}}effectiveTime",
    f"{{{CDA_NAMESPACE}}}setId",
    f"{{{CDA_NAMESPACE}}}versionNumber",
)
ElementSignature = tuple[str, tuple[tuple[str, str], ...], str]

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
    (
        "eicr_empty",
        ASSETS_FOLDER / "eicr_empty" / "eicr_empty.xml",
        ASSETS_FOLDER / "eicr_empty" / "eicr_empty_schematron_errors.xml",
    ),
    (
        "patient_alliance",
        ASSETS_FOLDER / "patient_alliance" / "eICR Sample Patient Alliance 03132020.xml",
        ASSETS_FOLDER
        / "patient_alliance"
        / "eICR Sample Patient Alliance 03132020_schematron_errors.xml",
    ),
    (
        "sample7",
        ASSETS_FOLDER / "sample7" / "eICR_Sample7_nullFlavorResultValues.xml",
        ASSETS_FOLDER / "sample7" / "eICR_Sample7_nullFlavorResultValues_schematron_errors.xml",
    ),
    (
        "sample9",
        ASSETS_FOLDER / "sample9" / "eICR_Sample9_nullFlavorResultValues_localCodes.xml",
        ASSETS_FOLDER
        / "sample9"
        / "eICR_Sample9_nullFlavorResultValues_localCodes_schematron_errors.xml",
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


def _parse_xml_document(xml_document: str, document_label: str, eicr_id: str) -> etree._Element:
    """Parse an XML document string into an lxml Element, failing the test if it's not well-formed.

    :param xml_document: The XML document as a string.
    :param document_label: A human-readable label for the document (e.g., "Original eICR") to use in error messages.
    :param eicr_id: The ID of the eICR being tested, to include in error messages for context.
    :return: The root Element of the parsed XML document.
    """
    try:
        return etree.fromstring(xml_document.encode("utf-8"))
    except etree.XMLSyntaxError as exc:
        pytest.fail(f"{document_label} XML is not well-formed for {eicr_id}: {exc}")


def _normalized_xml_text(text: str | None) -> str:
    """Normalize XML text content for comparison by stripping leading/trailing whitespace, or returning an empty string if None.

    :param text: The XML text content to normalize, which may be None.
    :return: Normalized text
    """
    if text is None:
        return ""

    return text.strip()


def _is_regenerated_document_header_element(element: etree._Element) -> bool:
    """Determine whether an element is one of the document header elements that the augmenter regenerates.

    :param element: The XML element to check.
    :return: True if the element is a regenerated document header element, False otherwise.
    """
    parent = element.getparent()

    if parent is None:
        return False

    if parent.tag != f"{{{CDA_NAMESPACE}}}ClinicalDocument":
        return False

    return str(element.tag) in REGENERATED_DOCUMENT_HEADER_TAGS


def _element_signature(element: etree._Element) -> ElementSignature:
    """Generate a signature for an XML element based on its tag, sorted attributes, and normalized text content.

    :param element: The XML element for which to generate a signature.
    :return: A tuple representing the element's signature.
    """
    attributes: tuple[tuple[str, str], ...] = tuple(
        sorted((str(key), value) for key, value in element.attrib.items())
    )
    return (str(element.tag), attributes, _normalized_xml_text(element.text))


def _collect_element_signatures(root: etree._Element) -> dict[ElementSignature, int]:
    """Traverse an XML tree and count the occurrences of each element signature, excluding regenerated document header elements.

    :param root: The root element of the XML tree to traverse.
    :return: A dictionary mapping element signatures to their occurrence counts.
    """
    signature_counts: dict[ElementSignature, int] = {}

    for element in root.iter():
        if not isinstance(element.tag, str):
            continue

        if _is_regenerated_document_header_element(element):
            continue

        signature = _element_signature(element)
        signature_counts[signature] = signature_counts.get(signature, 0) + 1

    return signature_counts


def _assert_augmented_observation_contains_expected_translations(
    augmented_observation: etree._Element,
    eicr_id: str,
) -> None:
    """Assert that an augmented observation contains <translation> elements in the CDA namespace, which the augmenter is expected to inject.

    :param augmented_observation: The root element of the augmented eICR observation where augmentation occurred.
    :param eicr_id: The ID of the eICR being tested, to include in error messages for context.
    """
    assert etree.QName(augmented_observation).localname == "observation", eicr_id

    translations: list[etree._Element] = augmented_observation.xpath(
        ".//cda:translation", namespaces=CDA_NAMESPACES
    )

    assert translations, (
        f"Augmented observation did not contain expected <translation> elements: {eicr_id}"
    )

    for translation in translations:
        assert etree.QName(translation).namespace == CDA_NAMESPACE, eicr_id


def _assert_augmented_eicr_retains_regenerated_document_header_elements(
    original_root: etree._Element,
    augmented_root: etree._Element,
    eicr_id: str,
) -> None:
    """Assert that the augmented eICR retains original regenerated document header elements when present, even though their content may differ.

    :param original_root: The root element of the original eICR XML tree.
    :param augmented_root: The root element of the augmented eICR XML tree.
    :param eicr_id: The ID of the eICR being tested, to include in error messages for context.
    """
    for tag in REGENERATED_DOCUMENT_HEADER_TAGS:
        original_matching_children = [child for child in original_root if child.tag == tag]

        if original_matching_children == []:
            continue

        matching_children = [child for child in augmented_root if child.tag == tag]

        assert matching_children != [], (
            f"Augmented eICR did not retain regenerated document header element for "
            f"{eicr_id}: {tag}"
        )


def _assert_augmented_eicr_retains_original_content(
    original_root: etree._Element,
    augmented_root: etree._Element,
    eicr_id: str,
) -> None:
    """Assert that the augmented eICR retains all original content except for the document header elements that the augmenter regenerates.

    :param original_root: The root element of the original eICR XML tree.
    :param augmented_root: The root element of the augmented eICR XML tree.
    :param eicr_id: The ID of the eICR being tested, to include in error messages for context.
    """
    _assert_augmented_eicr_retains_regenerated_document_header_elements(
        original_root,
        augmented_root,
        eicr_id,
    )

    original_signatures = _collect_element_signatures(original_root)
    augmented_signatures = _collect_element_signatures(augmented_root)
    missing_signatures: list[ElementSignature] = []

    for signature, original_count in original_signatures.items():
        augmented_count = augmented_signatures.get(signature, 0)

        if augmented_count < original_count:
            missing_signatures.append(signature)

    assert missing_signatures == [], (
        f"Augmented eICR did not retain all original content for {eicr_id}: {missing_signatures}"
    )


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

        original_eicr = Path(eicr_path).read_text(encoding="utf-8")
        augmented_eicr = self._read_s3_object(
            aws,
            f"{AUGMENTED_EICR_PREFIX}{TEST_PERSISTENCE_ID}",
        )
        snapshot.assert_match(augmented_eicr, f"{eicr_id}_augmented_eicr.xml")

        original_root = _parse_xml_document(original_eicr, "Original eICR", eicr_id)
        augmented_root = _parse_xml_document(augmented_eicr, "Augmented eICR", eicr_id)

        ttc_output = TTCAugmenterInput.model_validate_json(
            self._read_s3_object(
                aws,
                f"{TTC_OUTPUT_PREFIX}{TEST_PERSISTENCE_ID}",
            )
        )

        augmentation_metadata = AugmentationMetadata.model_validate_json(
            self._read_s3_object(aws, f"{AUGMENTATION_METADATA_PREFIX}{TEST_PERSISTENCE_ID}")
        )

        actual_validation_results = validate_eicr(augmented_eicr)

        if augmentation_metadata.passthrough:
            original_eicr = self._read_s3_object(
                aws,
                f"{TTC_INPUT_PREFIX}{TEST_PERSISTENCE_ID}",
            )
            passthrough_reason = augmentation_metadata.passthrough_reason

            assert augmented_eicr == original_eicr
            assert passthrough_reason in [
                PassthroughReason.NO_RELEVANT_SCHEMATRON_ERRORS,
                PassthroughReason.NO_CODE_MATCHES,
                PassthroughReason.TTC_EXCEPTION,
                PassthroughReason.AUGMENTATION_EXCEPTION,
                PassthroughReason.AUGMENTATION_VALIDATION_FAILURE,
            ]

            if passthrough_reason not in [
                PassthroughReason.AUGMENTATION_EXCEPTION,
                PassthroughReason.AUGMENTATION_VALIDATION_FAILURE,
            ]:
                assert ttc_output.passthrough is True
                assert ttc_output.passthrough_reason == passthrough_reason
        else:
            assert augmentation_metadata.passthrough in [None, False]
            assert augmented_eicr != ""

            augmented_observations: list[etree._Element] = augmented_root.xpath(
                "//cda:observation[.//cda:translation]",
                namespaces=CDA_NAMESPACES,
            )

            assert augmented_observations, (
                f"Augmented eICR did not contain observations with expected "
                f"<translation> elements: {eicr_id}"
            )

            for augmented_observation in augmented_observations:
                _assert_augmented_observation_contains_expected_translations(
                    augmented_observation,
                    eicr_id,
                )

            _assert_augmented_eicr_retains_original_content(original_root, augmented_root, eicr_id)

            assert actual_validation_results == [], actual_validation_results

        snapshot.assert_match(
            json.dumps(
                [result.model_dump() for result in actual_validation_results],
                indent=2,
                sort_keys=True,
            ),
            f"{eicr_id}_validation_results.json",
        )

        snapshot.assert_match(
            json.dumps(augmentation_metadata.model_dump(), indent=2, sort_keys=True),
            f"{eicr_id}_augmentation_metadata.json",
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
