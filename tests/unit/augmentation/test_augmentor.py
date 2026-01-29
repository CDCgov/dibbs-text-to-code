from pathlib import Path

import pytest

from augmentation.models.application import ApplicationCode
from augmentation.services.augmentor import Augmentor
from augmentation.services.augmentor import TTCAugmentor

EXAMPLE_EICRS_DIRECTORY = Path(__file__).parent.parent.parent / "assets"
DATA_CONFIG = {"some_config": "value"}
BASE_XPATH = "/ClinicalDocument/component/structuredBody/component/section/entry/component/observation/code/originalText/text()"

eicr_path = EXAMPLE_EICRS_DIRECTORY / "basic_test_eicr.xml"
with eicr_path.open() as f:
    EICR_OUTPUT = f.read()


class TestAugmentor:
    def test_base_augmentor_with_no_document_data(self):
        """Tests raising error when no document data is provided."""
        with pytest.raises(ValueError, match=r"Document data must be be a non-empty string!"):
            Augmentor(data_config=DATA_CONFIG, document_data=None)

        with pytest.raises(ValueError, match=r"Document data must be be a non-empty string!"):
            Augmentor(data_config=DATA_CONFIG, document_data="  ")

    def test_base_augmentor_with_no_data_config(self):
        """Tests raising error when no data config is provided."""
        with pytest.raises(
            ValueError, match=r"Data configuration must be supplied for augmentation!"
        ):
            Augmentor(data_config=None, document_data=EICR_OUTPUT)

        with pytest.raises(
            ValueError, match=r"Data configuration must be supplied for augmentation!"
        ):
            Augmentor(data_config={}, document_data=EICR_OUTPUT)

    def test_ttc_augmentor_with_no_document_data(self):
        """Tests raising error when no document data is provided."""
        with pytest.raises(ValueError, match=r"Document data must be be a non-empty string!"):
            TTCAugmentor(data_config=DATA_CONFIG, document_data=None)

        with pytest.raises(ValueError, match=r"Document data must be be a non-empty string!"):
            TTCAugmentor(data_config=DATA_CONFIG, document_data="  ")

    def test_ttc_augmentor_with_no_data_config(self):
        """Tests raising error when no data config is provided."""
        with pytest.raises(
            ValueError, match=r"Data configuration must be supplied for augmentation!"
        ):
            TTCAugmentor(data_config=None, document_data=EICR_OUTPUT)

        with pytest.raises(
            ValueError, match=r"Data configuration must be supplied for augmentation!"
        ):
            TTCAugmentor(data_config={}, document_data=EICR_OUTPUT)

    def test_ttc_augmentor_initialization(self):
        """Tests initialization of the TTC augmentor."""
        augmentor = TTCAugmentor(
            document_data=EICR_OUTPUT,
            data_config=DATA_CONFIG,
        )
        expected_data_fields = 2
        assert augmentor.application_code == augmentor._get_application()
        assert augmentor.application_code == ApplicationCode.TEXT_TO_CODE
        assert len(augmentor.data_fields) == expected_data_fields
        assert augmentor.eicr_base is not None
        xpath_result = augmentor.eicr_base.xpath(BASE_XPATH)
        assert xpath_result[0].strip() == "A custom code in original text."

    def test_augmentor_get_application(self):
        """Tests initialization of the TTC augmentor."""
        augmentor = TTCAugmentor(
            document_data=EICR_OUTPUT,
            data_config=DATA_CONFIG,
        )

        assert augmentor.application_code == ApplicationCode.TEXT_TO_CODE
        assert augmentor._get_application_code_value() == ApplicationCode.TEXT_TO_CODE.value
