from pathlib import Path

import pytest
from src.augmentation.models.application import ApplicationCode
from src.augmentation.models.config import AugmenterConfig
from src.augmentation.models.config import TTCAugmenterConfig
from src.augmentation.services.augmenter import Augmenter
from src.augmentation.services.augmenter import EICRAugmenter

EXAMPLE_EICRS_DIRECTORY = Path(__file__).parent.parent.parent / "assets"
DATA_CONFIG: AugmenterConfig = TTCAugmenterConfig()
BASE_XPATH = "/ClinicalDocument/component/structuredBody/component/section/entry/component/observation/code/originalText/text()"

eicr_path = EXAMPLE_EICRS_DIRECTORY / "basic_test_eicr.xml"
with eicr_path.open() as f:
    BASIC_ECR = f.read()

covid_ecr_path = EXAMPLE_EICRS_DIRECTORY / "test_eicr_covid.xml"
with covid_ecr_path.open() as f:
    COVID_ECR = f.read()


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
            Augmenter(config=None, document_payload=BASIC_ECR)

        with pytest.raises(ValueError, match=r"Augmentation configuration must be supplied!"):
            Augmenter(config={}, document_payload=BASIC_ECR)

    def test_ttc_augmenter_initialization(self):
        """Tests initialization of the TTC augmenter."""
        augmenter = EICRAugmenter(
            document_payload=BASIC_ECR,
            config=DATA_CONFIG,
        )
        assert augmenter.application_code.value == ApplicationCode.TEXT_TO_CODE.value
        assert augmenter.config == DATA_CONFIG
        assert augmenter.original_eicr is not None
        xpath_result = augmenter.original_eicr.xpath(BASE_XPATH)
        assert xpath_result[0].strip() == "A custom code in original text."

    def test_augmenter_get_application(self):
        """Tests get_application_code_value method."""
        augmenter = EICRAugmenter(
            document_payload=BASIC_ECR,
            config=DATA_CONFIG,
        )

        assert augmenter._get_application_code_value() == ApplicationCode.TEXT_TO_CODE.value

    def test_augmenter_validate_config_pass(self):
        """Tests EICRAugmenter validate config method."""
        augmenter = EICRAugmenter(
            document_payload=BASIC_ECR,
            config=DATA_CONFIG,
        )

        assert augmenter._validate_config() is None

    def test_augmenter_augment(self):
        """Tests augmentor _augment method."""
        augmenter = Augmenter(
            document_payload=BASIC_ECR,
            config=DATA_CONFIG,
        )
        assert augmenter._augment() == BASIC_ECR

    def test_augmenter_run(self):
        """Tests augmentor _run method."""
        augmenter = Augmenter(
            document_payload=BASIC_ECR,
            config=DATA_CONFIG,
        )
        assert augmenter.run() == BASIC_ECR

    def test_augmenter_get_by_xpath(self):
        """Tests TTC augmenter get_by_xpath method."""
        augmenter = EICRAugmenter(
            document_payload=BASIC_ECR,
            config=DATA_CONFIG,
        )

        assert (
            augmenter._get_original_by_xpath(BASE_XPATH)[0].strip()
            == "A custom code in original text."
        )

    def test_augmenter_get_document_id(self):
        """Tests TTC augmenter get_parent_document_id method."""
        augmenter = EICRAugmenter(
            document_payload=COVID_ECR,
            config=DATA_CONFIG,
        )
        result = augmenter._get_parent_document_id()

        # print(f"Document ID: {etree.tostring(result)}")

        assert result.get("root") == "10c13861-86a8-4a9a-aec6-b615921178df"
        assert result.get("extension") is None
        assert result.get("assigningAuthorityName") == "original-document"

    def test_augmenter_get_document_id_no_id(self):
        """Tests TTC augmenter get_parent_document_id method with missing document id."""
        with pytest.raises(ValueError, match=r"No document ID found in eICR document."):
            EICRAugmenter(config=DATA_CONFIG, document_payload=BASIC_ECR)._get_parent_document_id()

    def test_augmenter_get_setid(self):
        """Tests TTC augmenter get_parent_set_id method."""
        augmenter = EICRAugmenter(
            document_payload=COVID_ECR,
            config=DATA_CONFIG,
        )
        result = augmenter._get_parent_set_id()

        # print(f"Set ID: {etree.tostring(result)}")

        assert result.get("root") == "1.2.840.114350.1.13.380.3.7.1.1"
        assert result.get("extension") == "8d86218e-0fea-11eb-8216-a80388425cfb"
        assert result.get("assigningAuthorityName") is None

    def test_augmenter_get_setid_no_setid(self):
        """Tests TTC augmenter get_parent_set_id method with missing setId."""
        augmenter = EICRAugmenter(
            document_payload=BASIC_ECR,
            config=DATA_CONFIG,
        )
        result = augmenter._get_parent_set_id()
        assert result is None

    def test_augmenter_get_parent_version(self):
        """Tests TTC augmenter get_parent_version_number method."""
        augmenter = EICRAugmenter(
            document_payload=COVID_ECR,
            config=DATA_CONFIG,
        )
        result = augmenter._get_parent_version_number()
        assert result.get("value") == "1"

    def test_augmenter_get_parent_version_no_version(self):
        """Tests TTC augmenter get_parent_version_number method with missing versionNumber."""
        augmenter = EICRAugmenter(
            document_payload=BASIC_ECR,
            config=DATA_CONFIG,
        )
        result = augmenter._get_parent_version_number()
        assert result is None

    def test_augmenter_get_new_document_id(self):
        """Tests TTC augmenter _get_new_document_id method."""
        augmenter = EICRAugmenter(
            document_payload=BASIC_ECR,
            config=DATA_CONFIG,
        )
        result = augmenter._get_new_document_id()

        assert result.get("root") == augmenter.new_doc_id
        assert result.get("assigningAuthorityName") == ApplicationCode.TEXT_TO_CODE.value

    def test_augmenter_get_new_set_id(self):
        """Tests TTC augmenter _get_new_set_id method."""
        augmenter = EICRAugmenter(
            document_payload=BASIC_ECR,
            config=DATA_CONFIG,
        )
        result = augmenter._get_new_set_id()

        assert result.get("root") == augmenter.new_set_id

    def test_augmenter_get_new_version_number(self):
        """Tests TTC augmenter _get_new_version_number method."""
        augmenter = EICRAugmenter(
            document_payload=BASIC_ECR,
            config=DATA_CONFIG,
        )
        result = augmenter._get_new_version_number()

        assert result.get("value") == "1"

    def test_augmenter_get_new_effective_time(self):
        """Tests TTC augmenter _get_new_effective_time method."""
        augmenter = EICRAugmenter(
            document_payload=BASIC_ECR,
            config=DATA_CONFIG,
        )
        result = augmenter._get_new_effective_time()

        assert result.get("value") == augmenter.augmented_date.strftime("%Y%m%d%H%M%S")

    def test_eicraugmenter_augment(self):
        """Tests EICRAugmenter _augment method."""
        augmenter = EICRAugmenter(
            document_payload=COVID_ECR,
            config=DATA_CONFIG,
        )
        result = augmenter._augment()
        print(f"Augmented EICR: {result}")
        assert result is not None
        assert result != augmenter.original_eicr
