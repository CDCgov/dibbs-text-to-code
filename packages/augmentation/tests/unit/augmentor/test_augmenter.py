from pathlib import Path
from uuid import UUID

import pytest
from augmentation.models import DataField
from augmentation.models.augmentation import TTCAugmentation
from augmentation.models.config import ApplicationCode
from augmentation.models.config import AugmenterConfig
from augmentation.models.config import TTCAugmenterConfig
from augmentation.services.eicr_augmenter import EICRAugmenter
from pytest_mock import MockerFixture

EXAMPLE_EICRS_DIRECTORY = Path(__file__).parent.parent.parent / "assets"
DATA_CONFIG: AugmenterConfig = TTCAugmenterConfig()

eicr_path = EXAMPLE_EICRS_DIRECTORY / "basic_test_eicr.xml"
with eicr_path.open() as f:
    BASIC_ECR = f.read()

covid_ecr_path = EXAMPLE_EICRS_DIRECTORY / "test_eicr_covid.xml"
with covid_ecr_path.open() as f:
    COVID_ECR = f.read()

aug_covid_ecr_path = EXAMPLE_EICRS_DIRECTORY / "test_eicr_covid_augmented.xml"
with aug_covid_ecr_path.open() as f:
    AUG_COVID_ECR = f.read()


class TestEicrAugmenter:
    def test_base_augmenter_with_no_document_data(self):
        """Tests raising error when no document data is provided."""
        with pytest.raises(ValueError, match=r"Document payload must be a non-empty string!"):
            EICRAugmenter(None, augmentations=[])

    def test_ttc_augmenter_initialization(self):
        """Tests initialization of the TTC augmenter."""
        augmenter = EICRAugmenter(BASIC_ECR, [])
        assert augmenter.application_code.value == ApplicationCode.TEXT_TO_CODE.value
        assert augmenter.config == DATA_CONFIG
        assert augmenter.original_xml == BASIC_ECR

    @pytest.mark.freeze_time("2026-02-13T15:27:57")
    def test_run(self, mocker: MockerFixture):
        """Tests augmentor run method."""
        doc_id = UUID("12345678-1234-5678-1234-567812345678")
        set_id = UUID("87654321-4321-8765-4321-876543218765")

        mocker.patch("augmentation.services.eicr_augmenter.uuid4", side_effect=[doc_id, set_id])

        augmenter = EICRAugmenter(
            COVID_ECR,
            [
                TTCAugmentation(
                    location="/ClinicalDocument/component/structuredBody/component/section/entry/organizer/component/observation",
                    data_type=DataField.LAB_TEST_NAME_RESULTED,
                    code="10101010",
                    display_text="Chad new LOINC code",
                    original_text="Loser old LOINC",
                )
            ],
        )
        augmenter.augment()

        result = augmenter.augmented_xml
        assert result == AUG_COVID_ECR
