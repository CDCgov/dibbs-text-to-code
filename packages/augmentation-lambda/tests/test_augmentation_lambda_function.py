from datetime import datetime
from uuid import UUID
from zoneinfo import ZoneInfo

import pytest
from pytest_mock import MockerFixture
from pytest_snapshot.plugin import Snapshot

import lambda_handler
from augmentation_lambda import lambda_function
from shared_models import AUGMENTATION_METADATA_PREFIX
from shared_models import AUGMENTED_EICR_PREFIX
from shared_models import S3_BUCKET


@pytest.mark.time_machine(
    datetime(2026, 2, 13, 15, 27, 57, tzinfo=ZoneInfo("America/New_York")), tick=False
)
def test_handler_returns_success_result(
    example_sqs_event, mock_aws_setup, snapshot: Snapshot, mocker: MockerFixture
) -> None:
    """Tests that the handler returns a successful result when the augmenter runs without errors.

    :param mocker: The pytest-mock fixture for mocking objects.
    """
    doc_id = UUID("12345678-1234-5678-1234-567812345678")
    set_id = UUID("87654321-4321-8765-4321-876543218765")

    mocker.patch("augmentation.services.eicr_augmenter.uuid4", side_effect=[doc_id, set_id])
    _ = lambda_function.handler(example_sqs_event, {})

    # Assert that the augmentated eICR  was saved to S3
    augmented_eicr = lambda_handler.get_file_content_from_s3(
        bucket_name=S3_BUCKET,
        object_key=f"{AUGMENTED_EICR_PREFIX}{mock_aws_setup.persistence_id}",
    )

    snapshot.assert_match(augmented_eicr, "augmented_eicr.xml")

    # Assert that the augmentated eICR  was saved to S3
    augmentation_metadata = lambda_handler.get_file_content_from_s3(
        bucket_name=S3_BUCKET,
        object_key=f"{AUGMENTATION_METADATA_PREFIX}{mock_aws_setup.persistence_id}",
    )

    snapshot.assert_match(augmentation_metadata, "augmentation_metadata.json")
