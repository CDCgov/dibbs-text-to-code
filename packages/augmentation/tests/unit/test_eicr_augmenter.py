import os
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from lxml import etree
from pytest_snapshot.plugin import Snapshot

from augmentation.models import Metadata, NonstandardCodeInstanceMetadata
from augmentation.services.eicr_augmenter import EICRAugmenter
from shared_models import CdaInstanceIdentifier, Code, DataField, NonstandardCodeInstance

EXAMPLE_EICRS_DIRECTORY = Path(__file__).parent.parent / "assets"
BASE_XPATH = "/ClinicalDocument/component/structuredBody/component/section/entry/component/observation/code/originalText/text()"
TEST_PERSISTENCE_ID = os.environ["TEST_PERSISTENCE_ID"]
ORIGINAL_EICR_ID = CdaInstanceIdentifier(
    root="c8516bdc-8bb2-40aa-8dae-20a77546488f", extension=None
)

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


def _remove_first_element_by_local_name(xml: str, local_name: str) -> str:
    root = etree.fromstring(xml.encode("utf-8"))

    for element in root.iter():
        if etree.QName(element).localname == local_name:
            parent = element.getparent()
            assert parent is not None
            parent.remove(element)
            return etree.tostring(root, encoding="unicode")

    pytest.fail(f"Missing element: {local_name}")


def _add_language_code_after_effective_time(xml: str) -> str:
    root = etree.fromstring(xml.encode("utf-8"))
    namespace = etree.QName(root).namespace
    language_code_tag = f"{{{namespace}}}languageCode" if namespace else "languageCode"

    for element in root:
        if etree.QName(element).localname == "languageCode":
            return etree.tostring(root, encoding="unicode")

    for element in root:
        if etree.QName(element).localname == "effectiveTime":
            language_code = etree.Element(language_code_tag)
            language_code.set("code", "en-US")
            element.addnext(language_code)
            return etree.tostring(root, encoding="unicode")

    pytest.fail("Missing element: effectiveTime")


@pytest.mark.time_machine(datetime(2026, 2, 13, 15, 27, 57, tzinfo=ZoneInfo("America/New_York")))
class TestEicrAugmenter:
    def test_no_document_data(self):
        """Tests raising error when no document data is provided."""
        with pytest.raises(ValueError, match=r"Document payload must be a non-empty string!"):
            EICRAugmenter("", [])

    def test_initialization(self):
        """Tests initialization of the TTC augmenter."""
        augmenter = EICRAugmenter(BASIC_ECR, [])
        assert augmenter.original_xml == BASIC_ECR

    def test_original_eicr_id_includes_extension_when_present(self):
        """Tests original eICR ID includes extension when present."""
        eicr_with_extension = BASIC_ECR.replace(
            'root="c8516bdc-8bb2-40aa-8dae-20a77546488f"',
            'root="c8516bdc-8bb2-40aa-8dae-20a77546488f" extension="extension-1"',
            1,
        )

        augmenter = EICRAugmenter(eicr_with_extension, [])

        assert augmenter.original_eicr_id == CdaInstanceIdentifier(
            root="c8516bdc-8bb2-40aa-8dae-20a77546488f",
            extension="extension-1",
        )

    def test_basic_eicr(self, snapshot: Snapshot):
        """Tests augmenter run method."""
        augmenter = EICRAugmenter(
            BASIC_ECR,
            [
                NonstandardCodeInstance(
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
        result = augmenter.augment()

        # test was failing due to whitespace at the end of the result so stripping it here
        snapshot.assert_match(result.augmented_xml.strip(), "basic_eicr_augmented.xml")
        assert result.metadata == Metadata(
            original_eicr_id=ORIGINAL_EICR_ID,
            augmented_eicr_id=CdaInstanceIdentifier(root=augmenter.new_doc_id),
            nonstandard_codes=[
                NonstandardCodeInstanceMetadata(
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
        result = augmenter.augment()

        # test was failing due to whitespace at the end of the result so stripping it here
        snapshot.assert_match(result.augmented_xml.strip(), "basic_eicr_related_doc_augmented.xml")
        assert result.metadata == Metadata(
            original_eicr_id=ORIGINAL_EICR_ID,
            augmented_eicr_id=CdaInstanceIdentifier(root=augmenter.new_doc_id),
            nonstandard_codes=[
                NonstandardCodeInstanceMetadata(
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

    def test_adds_set_id_when_missing(self):
        """Tests augmenter adds setId when the original eICR does not have one."""
        eicr_with_language_code = _add_language_code_after_effective_time(BASIC_ECR)
        eicr_without_set_id = _remove_first_element_by_local_name(
            eicr_with_language_code,
            "setId",
        )

        augmenter = EICRAugmenter(eicr_without_set_id, [])

        result = augmenter.augment()

        root = etree.fromstring(result.augmented_xml.encode("utf-8"))
        set_ids = [
            element
            for element in root
            if isinstance(element.tag, str) and etree.QName(element).localname == "setId"
        ]

        assert set_ids[0].get("root") == augmenter.new_set_id

    def test_adds_version_number_when_missing(self):
        """Tests augmenter adds versionNumber when the original eICR does not have one."""
        eicr_without_version_number = _remove_first_element_by_local_name(
            BASIC_ECR,
            "versionNumber",
        )

        augmenter = EICRAugmenter(eicr_without_version_number, [])

        result = augmenter.augment()

        root = etree.fromstring(result.augmented_xml.encode("utf-8"))
        version_numbers = [
            element
            for element in root
            if isinstance(element.tag, str) and etree.QName(element).localname == "versionNumber"
        ]

        assert version_numbers[0].get("value") == "1"

    def test_translation_xpath_adds_index_when_same_tag_siblings_exist(self):
        """Tests translation XPath adds index when same tag siblings exist."""
        nonstandard_codes = [
            NonstandardCodeInstance(
                schematron_error_xpath="/ClinicalDocument/component/structuredBody/component/section/entry/component/observation",
                field_type=DataField.LAB_TEST_NAME_RESULTED,
                new_translation=Code(
                    code="10101010",
                    display_name="Chad new LOINC code",
                    original_text="Loser old LOINC",
                ),
            ),
            NonstandardCodeInstance(
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

        result = augmenter.augment()

        assert result.metadata.nonstandard_codes[1].new_translation_xpath == (
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

    def test_get_original_by_xpath_returns_original_element(self):
        """Tests original XPath lookup returns an element from the original eICR."""
        augmenter = EICRAugmenter(BASIC_ECR, [])

        original_id = augmenter._get_original_by_xpath("/ClinicalDocument/id")

        assert original_id.get("root") == ORIGINAL_EICR_ID.root

    def test_get_augmented_tag_by_xpath_raises_when_element_is_missing(self):
        """Tests missing augmented element raises a helpful error."""
        augmenter = EICRAugmenter(BASIC_ECR, [])

        with pytest.raises(
            ValueError,
            match=r"Unable to find tag in eICR document for XPath: /ClinicalDocument/notARealTag",
        ):
            augmenter._get_augmented_tag_by_xpath("/ClinicalDocument/notARealTag")

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

    def test_get_new_version_number_defaults_to_one_when_element_is_missing(self):
        """Tests versionNumber defaults to 1 when versionNumber is missing."""
        eicr_without_version_number = _remove_first_element_by_local_name(
            BASIC_ECR,
            "versionNumber",
        )

        augmenter = EICRAugmenter(eicr_without_version_number, [])

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
