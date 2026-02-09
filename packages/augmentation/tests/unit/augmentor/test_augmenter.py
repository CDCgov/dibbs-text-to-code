from pathlib import Path

import pytest
from augmentation.models.application import ApplicationCode
from augmentation.models.config import AugmenterConfig
from augmentation.models.config import TTCAugmenterConfig
from augmentation.services.augmenter import Augmenter
from augmentation.services.augmenter import TTCAugmenter

EXAMPLE_EICRS_DIRECTORY = Path(__file__).parent.parent.parent / "assets"
DATA_CONFIG: AugmenterConfig = TTCAugmenterConfig()
BASE_XPATH = "/ClinicalDocument/component/structuredBody/component/section/entry/component/observation/code/originalText/text()"

eicr_path = EXAMPLE_EICRS_DIRECTORY / "basic_test_eicr.xml"
with eicr_path.open() as f:
    EICR_OUTPUT = f.read()


class TestAugmenter:
    def test_base_augmenter_with_no_document_data(self):
        """Tests raising error when no document data is provided."""
        with pytest.raises(ValueError, match=r"Document payload must be a non-empty string!"):
            Augmenter(config=DATA_CONFIG, document_payload=None)

        with pytest.raises(ValueError, match=r"Document payload must be a non-empty string!"):
            Augmenter(config=DATA_CONFIG, document_payload="  ")

    def test_base_augmenter_with_no_data_config(self):
        """Tests raising error when no data config is provided."""
        with pytest.raises(ValueError, match=r"Augmentation configuration must be supplied!"):
            Augmenter(config=None, document_payload=EICR_OUTPUT)

        with pytest.raises(ValueError, match=r"Augmentation configuration must be supplied!"):
            Augmenter(config={}, document_payload=EICR_OUTPUT)

    def test_ttc_augmenter_initialization(self):
        """Tests initialization of the TTC augmenter."""
        augmenter = TTCAugmenter(
            document_payload=EICR_OUTPUT,
            config=DATA_CONFIG,
        )
        assert augmenter.application_code.value == ApplicationCode.TEXT_TO_CODE.value
        assert augmenter.config == DATA_CONFIG
        assert augmenter.eicr_base is not None
        xpath_result = augmenter.eicr_base.xpath(BASE_XPATH)
        assert xpath_result[0].strip() == "A custom code in original text."

    def test_augmenter_get_application(self):
        """Tests get_application_code_value method."""
        augmenter = TTCAugmenter(
            document_payload=EICR_OUTPUT,
            config=DATA_CONFIG,
        )

        assert augmenter._get_application_code_value() == ApplicationCode.TEXT_TO_CODE.value

    def test_augmenter_validate_config_pass(self):
        """Tests validate config method."""
        augmenter = TTCAugmenter(
            document_payload=EICR_OUTPUT,
            config=DATA_CONFIG,
        )

        assert augmenter._validate_config() is None

    def test_augmenter_augment(self):
        """Tests TTC augmentor _augment method."""
        augmenter = TTCAugmenter(
            document_payload=EICR_OUTPUT,
            config=DATA_CONFIG,
        )
        assert augmenter._augment() == EICR_OUTPUT

    def test_augmenter_run(self):
        """Tests TTC augmentor _run method."""
        augmenter = TTCAugmenter(
            document_payload=EICR_OUTPUT,
            config=DATA_CONFIG,
        )
        assert augmenter.run() == EICR_OUTPUT

    def test_augmenter_get_by_xpath(self):
        """Tests TTC augmenter get_by_xpath method."""
        augmenter = TTCAugmenter(
            document_payload=EICR_OUTPUT,
            config=DATA_CONFIG,
        )

        assert augmenter._get_by_xpath(BASE_XPATH)[0].strip() == "A custom code in original text."
