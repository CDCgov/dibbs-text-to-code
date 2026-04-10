from datetime import datetime
from pathlib import Path
from uuid import UUID
from zoneinfo import ZoneInfo

import pytest
from pytest_mock import MockerFixture
from pytest_snapshot.plugin import Snapshot

from augmentation.models import Metadata
from augmentation.models import NonstandardCodeReplacementMetadata
from augmentation.models.config import ApplicationCode
from augmentation.models.config import AugmenterConfig
from augmentation.models.config import TTCAugmenterConfig
from augmentation.services.augmenter import Augmenter
from augmentation.services.eicr_augmenter import EICRAugmenter
from shared_models import Code
from shared_models import DataField
from shared_models import NonstandardCodeReplacement

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


@pytest.mark.time_machine(
    datetime(2026, 2, 13, 15, 27, 57, tzinfo=ZoneInfo("America/New_York")), tick=False
)
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

    def test_basic_eicr(self, mocker: MockerFixture, snapshot: Snapshot):
        """Tests augmentor run method."""
        doc_id = UUID("12345678-1234-5678-1234-567812345678")
        set_id = UUID("87654321-4321-8765-4321-876543218765")

        mocker.patch("augmentation.services.eicr_augmenter.uuid4", side_effect=[doc_id, set_id])

        augmenter = EICRAugmenter(
            BASIC_ECR,
            [
                NonstandardCodeReplacement(
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
            original_eicr_id="c8516bdc-8bb2-40aa-8dae-20a77546488f",
            augmented_eicr_id="12345678-1234-5678-1234-567812345678",
            nonstandard_codes=[
                NonstandardCodeReplacementMetadata(
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

    def test_eicr_related_doc(self, mocker: MockerFixture, snapshot: Snapshot):
        """Tests augmentor run method."""
        doc_id = UUID("12345678-1234-5678-1234-567812345678")
        set_id = UUID("87654321-4321-8765-4321-876543218765")

        mocker.patch("augmentation.services.eicr_augmenter.uuid4", side_effect=[doc_id, set_id])

        nonstandard_codes = [
            NonstandardCodeReplacement(
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
            original_eicr_id="c8516bdc-8bb2-40aa-8dae-20a77546488f",
            augmented_eicr_id="12345678-1234-5678-1234-567812345678",
            nonstandard_codes=[
                NonstandardCodeReplacementMetadata(
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

    def test_empty_eicr(self, mocker: MockerFixture):
        """Tests augmentor run method."""
        doc_id = UUID("12345678-1234-5678-1234-567812345678")
        set_id = UUID("87654321-4321-8765-4321-876543218765")

        mocker.patch("augmentation.services.eicr_augmenter.uuid4", side_effect=[doc_id, set_id])

        with pytest.raises(
            ValueError,
            match=r"Unable to find tag in eICR document for XPath: /ClinicalDocument/id/@root",
        ):
            EICRAugmenter(EMPTY_ECR, [])

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
