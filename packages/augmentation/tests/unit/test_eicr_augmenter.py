from datetime import datetime
from pathlib import Path
from uuid import UUID
from zoneinfo import ZoneInfo

import pytest
from augmentation.models.augmentation import TTCAugmentation
from augmentation.models.config import ApplicationCode
from augmentation.models.config import AugmenterConfig
from augmentation.models.config import TTCAugmenterConfig
from augmentation.services.eicr_augmenter import EICRAugmenter
from pytest_mock import MockerFixture
from pytest_snapshot.plugin import Snapshot
from shared_models import DataField

EXAMPLE_EICRS_DIRECTORY = Path(__file__).parent.parent / "assets"
DATA_CONFIG: AugmenterConfig = TTCAugmenterConfig()
BASE_XPATH = "/ClinicalDocument/component/structuredBody/component/section/entry/component/observation/code/originalText/text()"

eicr_path = EXAMPLE_EICRS_DIRECTORY / "basic_test_eicr.xml"
with eicr_path.open() as f:
    BASIC_ECR = f.read()

eicr_path = EXAMPLE_EICRS_DIRECTORY / "basic_test_eicr_related_doc.xml"
with eicr_path.open() as f:
    BASIC_ECR_RELATED_DOC = f.read()

eicr_path = EXAMPLE_EICRS_DIRECTORY / "empty_eicr.xml"
with eicr_path.open() as f:
    EMPTY_ECR = f.read()


@pytest.mark.time_machine(datetime(2026, 2, 13, 15, 27, 57, tzinfo=ZoneInfo("America/New_York")))
class TestEicrAugmenter:
    def test_no_document_data(self):
        """Tests raising error when no document data is provided."""
        with pytest.raises(ValueError, match=r"Document payload must be a non-empty string!"):
            EICRAugmenter(None, [])

    def test_initialization(self):
        """Tests initialization of the TTC augmenter."""
        augmenter = EICRAugmenter(BASIC_ECR, [])
        assert augmenter.application_code.value == ApplicationCode.TEXT_TO_CODE.value
        assert augmenter.config == DATA_CONFIG
        assert augmenter.original_xml == BASIC_ECR

    def test_basic_eicr(self, mocker: MockerFixture, snapshot: Snapshot):
        """Tests augmentor run method."""
        doc_id = UUID("12345678-1234-5678-1234-567812345678")
        set_id = UUID("87654321-4321-8765-4321-876543218765")

        mocker.patch("augmentation.services.eicr_augmenter.uuid4", side_effect=[doc_id, set_id])

        augmenter = EICRAugmenter(
            BASIC_ECR,
            [
                TTCAugmentation(
                    location="/ClinicalDocument/component/structuredBody/component/section/entry/component/observation",
                    data_type=DataField.LAB_TEST_NAME_RESULTED,
                    code="10101010",
                    display_name="Chad new LOINC code",
                    original_text="Loser old LOINC",
                )
            ],
        )
        augmenter.augment()

        result = augmenter.augmented_xml

        snapshot.assert_match(result, "basic_eicr_augmented.xml")

    def test_eicr_related_doc(self, mocker: MockerFixture, snapshot: Snapshot):
        """Tests augmentor run method."""
        doc_id = UUID("12345678-1234-5678-1234-567812345678")
        set_id = UUID("87654321-4321-8765-4321-876543218765")

        mocker.patch("augmentation.services.eicr_augmenter.uuid4", side_effect=[doc_id, set_id])

        augmenter = EICRAugmenter(
            BASIC_ECR_RELATED_DOC,
            [
                TTCAugmentation(
                    location="/ClinicalDocument/component/structuredBody/component/section/entry/component/observation",
                    data_type=DataField.LAB_TEST_NAME_RESULTED,
                    code="10101010",
                    display_name="Chad new LOINC code",
                    original_text="Loser old LOINC",
                )
            ],
        )
        augmenter.augment()

        result = augmenter.augmented_xml
        snapshot.assert_match(result, "basic_eicr_related_doc_augmented.xml")

    def test_empty_eicr(self, mocker: MockerFixture):
        """Tests augmentor run method."""
        doc_id = UUID("12345678-1234-5678-1234-567812345678")
        set_id = UUID("87654321-4321-8765-4321-876543218765")

        mocker.patch("augmentation.services.eicr_augmenter.uuid4", side_effect=[doc_id, set_id])

        augmenter = EICRAugmenter(EMPTY_ECR, [])
        with pytest.raises(ValueError, match=r"Unable to find tag in eICR document for XPath"):
            augmenter.augment()
