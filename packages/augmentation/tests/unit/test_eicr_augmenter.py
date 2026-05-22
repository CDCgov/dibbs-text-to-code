import os
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from pytest_snapshot.plugin import Snapshot

from augmentation.models import Metadata, NonstandardCodeInstanceMetadata
from augmentation.models.config import ApplicationCode, AugmenterConfig, TTCAugmenterConfig
from augmentation.services.augmenter import Augmenter
from augmentation.services.eicr_augmenter import EICRAugmenter
from shared_models import Code, DataField, NonstandardCodeInstance

EXAMPLE_EICRS_DIRECTORY = Path(__file__).parent.parent / "assets"
DATA_CONFIG: AugmenterConfig = TTCAugmenterConfig()
BASE_XPATH = "/ClinicalDocument/component/structuredBody/component/section/entry/component/observation/code/originalText/text()"
TEST_PERSISTENCE_ID = os.environ["TEST_PERSISTENCE_ID"]
ORIGINAL_EICR_ID = "c8516bdc-8bb2-40aa-8dae-20a77546488f"

eicr_path = EXAMPLE_EICRS_DIRECTORY / "basic_test_eicr.xml"
with eicr_path.open() as f:
    BASIC_ECR = f.read()

eicr_path = EXAMPLE_EICRS_DIRECTORY / "basic_test_eicr_related_doc.xml"
with eicr_path.open() as f:
    BASIC_ECR_RELATED_DOC = f.read()

eicr_path = EXAMPLE_EICRS_DIRECTORY / "empty_eicr.xml"
with eicr_path.open() as f:
    EMPTY_ECR = f.read()

eicr_path = EXAMPLE_EICRS_DIRECTORY / "test_eicr_covid.xml"
with eicr_path.open() as f:
    COVID_ECR = f.read()


@pytest.mark.time_machine(datetime(2026, 2, 13, 15, 27, 57, tzinfo=ZoneInfo("America/New_York")))
class TestEicrAugmenter:
    def test_no_document_data(self):
        """Tests raising error when no document data is provided."""
        with pytest.raises(ValueError, match=r"Document payload must be a non-empty string!"):
            EICRAugmenter("", [])

    def test_initialization(self):
        """Tests initialization of the TTC augmenter."""
        augmenter = EICRAugmenter(BASIC_ECR, [])
        assert augmenter.application_code.value == ApplicationCode.TEXT_TO_CODE.value
        assert augmenter.config == DATA_CONFIG
        assert augmenter.original_xml == BASIC_ECR

    def test_basic_eicr(self, snapshot: Snapshot):
        """Tests augmenter run method."""
        augmenter = EICRAugmenter(
            BASIC_ECR,
            [
                NonstandardCodeInstance(
                    schematron_error="text-to-code-test",
                    schematron_error_xpath="/ClinicalDocument/component/structuredBody/component/section/entry/component/observation",
                    field_type=DataField.LAB_TEST_NAME_RESULTED,
                    new_translation=Code(
                        code="10101010",
                        display_name="Chad new LOINC code",
                        original_text="Loser old LOINC",
                    ),
                )
            ],
        )
        metadata = augmenter.augment()

        result = augmenter.augmented_xml

        # test was failing due to whitespace at the end of the result so stripping it here
        snapshot.assert_match(result.strip(), "basic_eicr_augmented.xml")
        assert metadata == Metadata(
            original_eicr_id=ORIGINAL_EICR_ID,
            augmented_eicr_id=augmenter.new_doc_id,
            nonstandard_codes=[
                NonstandardCodeInstanceMetadata(
                    schematron_error="text-to-code-test",
                    schematron_error_xpath="/ClinicalDocument/component/structuredBody/component/section/entry/component/observation",
                    field_type=DataField.LAB_TEST_NAME_RESULTED,
                    new_translation=Code(
                        code="10101010",
                        display_name="Chad new LOINC code",
                        original_text="Loser old LOINC",
                    ),
                    new_translation_xpath="/ClinicalDocument/component/structuredBody/component/section/entry/component/observation/code/translation",
                )
            ],
        )

    def test_eicr_related_doc(self, snapshot: Snapshot):
        """Tests augmenter run method."""
        nonstandard_codes = [
            NonstandardCodeInstance(
                schematron_error="text-to-code-test",
                schematron_error_xpath="/ClinicalDocument/component/structuredBody/component/section/entry/component/observation",
                field_type=DataField.LAB_TEST_NAME_RESULTED,
                new_translation=Code(
                    code="10101010",
                    display_name="Chad new LOINC code",
                    original_text="Loser old LOINC",
                ),
            )
        ]
        augmenter = EICRAugmenter(
            BASIC_ECR_RELATED_DOC,
            nonstandard_codes,
        )
        metadata = augmenter.augment()

        result = augmenter.augmented_xml
        # test was failing due to whitespace at the end of the result so stripping it here
        snapshot.assert_match(result.strip(), "basic_eicr_related_doc_augmented.xml")
        assert metadata == Metadata(
            original_eicr_id=ORIGINAL_EICR_ID,
            augmented_eicr_id=augmenter.new_doc_id,
            nonstandard_codes=[
                NonstandardCodeInstanceMetadata(
                    schematron_error="text-to-code-test",
                    schematron_error_xpath="/ClinicalDocument/component/structuredBody/component/section/entry/component/observation",
                    field_type=DataField.LAB_TEST_NAME_RESULTED,
                    new_translation=Code(
                        code="10101010",
                        display_name="Chad new LOINC code",
                        original_text="Loser old LOINC",
                    ),
                    new_translation_xpath="/ClinicalDocument/component/structuredBody/component/section/entry/component/observation/code/translation",
                )
            ],
        )

    def test_translation_xpath_adds_index_when_same_tag_siblings_exist(self):
        """Tests translation XPath adds index when same tag siblings exist."""
        nonstandard_codes = [
            NonstandardCodeInstance(
                schematron_error="text-to-code-test",
                schematron_error_xpath="/ClinicalDocument/component/structuredBody/component/section/entry/component/observation",
                field_type=DataField.LAB_TEST_NAME_RESULTED,
                new_translation=Code(
                    code="10101010",
                    display_name="Chad new LOINC code",
                    original_text="Loser old LOINC",
                ),
            ),
            NonstandardCodeInstance(
                schematron_error="text-to-code-test",
                schematron_error_xpath="/ClinicalDocument/component/structuredBody/component/section/entry/component/observation",
                field_type=DataField.LAB_TEST_NAME_RESULTED,
                new_translation=Code(
                    code="20202020",
                    display_name="Second new LOINC code",
                    original_text="Second old LOINC",
                ),
            ),
        ]
        augmenter = EICRAugmenter(BASIC_ECR, nonstandard_codes)

        metadata = augmenter.augment()

        assert metadata.nonstandard_codes[1].new_translation_xpath == (
            "/ClinicalDocument/component/structuredBody/component/section/entry/component/observation/code/translation[2]"
        )

    def test_get_old_document_id_preserves_assigning_authority_name_when_present(self):
        """Tests old document id preserves assigningAuthorityName when present."""
        eicr_with_assigning_authority_name = BASIC_ECR.replace(
            ' assigningAuthorityName="original-document"',
            "",
        ).replace(
            ' assigningAuthorityName="TEXT_TO_CODE"',
            "",
        )

        augmenter = EICRAugmenter(eicr_with_assigning_authority_name, [])

        parent_doc_id = augmenter._get_old_document_id()

        assert parent_doc_id.get("assigningAuthorityName") == "original-document"

    def test_empty_eicr(self):
        """Tests augmenter run method."""
        with pytest.raises(
            ValueError,
            match=r"Unable to find tag in eICR document for XPath: /ClinicalDocument/id/@root",
        ):
            EICRAugmenter(EMPTY_ECR, [])

    def test_get_new_version_number_defaults_to_one_when_value_is_missing(self):
        """Tests versionNumber defaults to 1 when value attribute is missing."""
        eicr_without_version_number_value = BASIC_ECR.replace(
            '<versionNumber value="1" />',
            "<versionNumber />",
        )

        assert eicr_without_version_number_value != BASIC_ECR

        augmenter = EICRAugmenter(eicr_without_version_number_value, [])

        version_number = augmenter._get_new_version_number()

        assert version_number.get("value") == "1"

    def test_generates_same_augmented_ids_for_same_document_when_seed_is_not_supplied(self):
        """Tests deterministic augmented identifiers default to stable values for the same document."""
        first_augmenter = EICRAugmenter(BASIC_ECR, [])
        second_augmenter = EICRAugmenter(BASIC_ECR, [])

        assert first_augmenter.new_doc_id == second_augmenter.new_doc_id
        assert first_augmenter.new_set_id == second_augmenter.new_set_id

    def test_uses_deterministic_id_seed_when_supplied(self):
        """Tests deterministic augmented identifiers use supplied seed values when present."""
        augmenter = EICRAugmenter(
            BASIC_ECR,
            [],
            deterministic_id_seed=TEST_PERSISTENCE_ID,
        )

        assert augmenter.new_doc_id == "d44dc1c6-8a0c-5236-906e-12f6475589ec"
        assert augmenter.new_set_id == "2683d208-bbec-5d37-8886-3b46fb5ec908"

    def test_generates_same_augmented_ids_for_same_seed_when_documents_are_different(self):
        """Tests deterministic augmented identifiers use supplied seed values when present."""
        first_augmenter = EICRAugmenter(
            BASIC_ECR,
            [],
            deterministic_id_seed=TEST_PERSISTENCE_ID,
        )
        second_augmenter = EICRAugmenter(
            COVID_ECR,
            [],
            deterministic_id_seed=TEST_PERSISTENCE_ID,
        )

        assert first_augmenter.new_doc_id == second_augmenter.new_doc_id
        assert first_augmenter.new_set_id == second_augmenter.new_set_id

    def test_get_old_document_id_sets_assigning_authority_name_when_missing(self):
        """Tests old document id gets assigningAuthorityName when missing."""
        augmenter = EICRAugmenter(BASIC_ECR, [])

        parent_doc_id = augmenter._get_old_document_id()

        assert parent_doc_id.get("assigningAuthorityName") == "original-document"

    def test_validate_config_raises_value_error_when_application_code_does_not_match(self):
        """Tests config validation when application code does not match."""

        class TestAugmenter(Augmenter):
            def augment(self) -> Metadata:
                return Metadata(
                    original_eicr_id="original-doc-id",
                    augmented_eicr_id="augmented-doc-id",
                    nonstandard_codes=[],
                )

        class InvalidConfig:
            application_code = "wrong-application-code"

        with pytest.raises(
            ValueError,
            match=r"Config application code wrong-application-code does not match Augmenter application code ApplicationCode.TEXT_TO_CODE.",
        ):
            TestAugmenter(
                BASIC_ECR,
                InvalidConfig(),
            )

    def test_augment_base_method_returns_none(self):
        """Tests abstract base augment method body."""
        assert Augmenter.augment(object()) is None
