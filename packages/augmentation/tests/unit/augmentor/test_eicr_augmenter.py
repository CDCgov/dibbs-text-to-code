from pathlib import Path
from uuid import UUID

import pytest
from augmentation.models.config import ApplicationCode
from augmentation.models.config import AugmenterConfig
from augmentation.models.config import TTCAugmenterConfig
from augmentation.services.eicr_augmenter import EICRAugmenter
from pytest_mock import MockerFixture
from pytest_snapshot.plugin import Snapshot

EXAMPLE_EICRS_DIRECTORY = Path(__file__).parent.parent.parent / "assets"
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


@pytest.mark.freeze_time("2026-02-13T15:27:57")
class TestEicrAugmenter:
    def test_no_document_data(self):
        """Tests raising error when no document data is provided."""
        with pytest.raises(ValueError, match=r"Document payload must be a non-empty string!"):
            EICRAugmenter(document=None)

    def test_initialization(self):
        """Tests initialization of the TTC augmenter."""
        augmenter = EICRAugmenter(document=BASIC_ECR)
        assert augmenter.application_code.value == ApplicationCode.TEXT_TO_CODE.value
        assert augmenter.config == DATA_CONFIG
        assert augmenter.original_xml == BASIC_ECR

    def test_basic_eicr(self, mocker: MockerFixture, snapshot: Snapshot):
        """Tests augmentor run method."""
        doc_id = UUID("12345678-1234-5678-1234-567812345678")
        set_id = UUID("87654321-4321-8765-4321-876543218765")

        mocker.patch("augmentation.services.eicr_augmenter.uuid4", side_effect=[doc_id, set_id])

        augmenter = EICRAugmenter(
            document=BASIC_ECR,
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
            document=BASIC_ECR_RELATED_DOC,
        )
        augmenter.augment()

        result = augmenter.augmented_xml
        snapshot.assert_match(result, "basic_eicr_related_doc_augmented.xml")

    def test_empty_eicr(self, mocker: MockerFixture):
        """Tests augmentor run method."""
        doc_id = UUID("12345678-1234-5678-1234-567812345678")
        set_id = UUID("87654321-4321-8765-4321-876543218765")

        mocker.patch("augmentation.services.eicr_augmenter.uuid4", side_effect=[doc_id, set_id])

        augmenter = EICRAugmenter(
            document=EMPTY_ECR,
        )
        with pytest.raises(ValueError, match=r"Unable to find tag in eICR document for XPath"):
            augmenter.augment()
