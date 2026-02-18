from pathlib import Path
from uuid import UUID

import pytest
from augmentation.models.config import AugmenterConfig
from augmentation.models.config import TTCAugmenterConfig
from augmentation.services.eicr_augmenter import EICRAugmenter
from pytest_mock import MockerFixture

EXAMPLE_EICRS_DIRECTORY = Path(__file__).parent.parent.parent / "assets"
DATA_CONFIG: AugmenterConfig = TTCAugmenterConfig()
BASE_XPATH = "/ClinicalDocument/component/structuredBody/component/section/entry/component/observation/code/originalText/text()"

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
    @pytest.mark.freeze_time("2026-02-13T15:27:57")
    def test_run(self, mocker: MockerFixture):
        """Tests augmentor run method."""
        doc_id = UUID("12345678-1234-5678-1234-567812345678")
        set_id = UUID("87654321-4321-8765-4321-876543218765")

        mocker.patch("augmentation.services.eicr_augmenter.uuid4", side_effect=[doc_id, set_id])

        augmenter = EICRAugmenter(
            document=COVID_ECR,
        )
        augmenter.augment()

        result = augmenter.augmented_xml
        assert result == AUG_COVID_ECR
