from pathlib import Path
from unittest.mock import patch

import pytest
from lxml.etree import XMLSyntaxError

from shared_models import CdaInstanceIdentifier
from shared_models import DataField
from text_to_code.models import Candidate
from text_to_code.models import LabXPaths
from text_to_code.models.eicr import Metadata
from text_to_code.services.eicr_processor import EicrProcessor
from text_to_code.services.utils import get_config_for_data_field

EXAMPLE_EICRS_DIRECTORY = Path(__file__).parent.parent / "assets"

BASE_XPATH = (
    "/ClinicalDocument/component/structuredBody/component/section/entry/component/observation"
)

NO_MATCH_FOUND_ERROR_MESSAGE = "No ID element found in eICR XML."


class TestEmptyEicrProcessor:
    def test_init(self):
        """Test initialization of an eICR processor.

        This feels like a silly unit test as an eICR processor does not have any public attributes,
        but IDK initialization may become more complicated.
        """
        assert EicrProcessor("<tag />")

    def test_get_text_candidates_empty_xpath(self):
        result = EicrProcessor("<tag />").get_text_candidates("", DataField.LAB_TEST_NAME_RESULTED)
        assert len(result) == 0

    def test_get_text_candidates_logs_when_xpath_lookup_fails(self):
        processor = EicrProcessor("<tag />")
        expected_sub_xpaths = get_config_for_data_field(DataField.LAB_TEST_NAME_RESULTED).xpaths

        with (
            patch.object(processor, "_get_by_xpath", side_effect=Exception("boom")),
            patch("text_to_code.services.eicr_processor.logger.exception") as mock_exception,
        ):
            result = processor.get_text_candidates(BASE_XPATH, DataField.LAB_TEST_NAME_RESULTED)

        assert result == []
        mock_exception.assert_called_once_with(
            "Failed to extract text candidates from eICR",
            base_xpath=BASE_XPATH,
            data_field=str(DataField.LAB_TEST_NAME_RESULTED),
            sub_xpaths=expected_sub_xpaths,
            status="error",
        )

    def test_resolve_reference_returns_none_for_empty_reference_value(self):
        processor = EicrProcessor("<ClinicalDocument />")

        assert processor.resolve_reference(None) is None
        assert processor.resolve_reference("") is None
        assert processor.resolve_reference("   ") is None

    def test_resolve_reference_returns_none_when_reference_is_missing(self):
        processor = EicrProcessor(
            "<ClinicalDocument><section><text>ID exists</text></section></ClinicalDocument>"
        )

        assert processor.resolve_reference("#missing-id") is None

    def test_extract_text_candidates_from_element_includes_child_tail_text(self):
        processor = EicrProcessor(
            """
            <ClinicalDocument>
                <section>
                    <text>
                        <target>first<inner>second</inner>third</target>
                    </text>
                </section>
            </ClinicalDocument>
            """
        )

        element = processor._xml_root.find(".//target")
        assert element is not None

        result = processor._extract_text_candidates_from_element(element)

        assert result == ["first second third third"]


class TestBadEicr:
    def test_bad_eicr(self):
        eicr_path = EXAMPLE_EICRS_DIRECTORY / "bad_test_eicr.xml"
        with eicr_path.open() as f:
            eicr_output = f.read()

        with pytest.raises(XMLSyntaxError):
            EicrProcessor(eicr_output)


class TestBasicEicrProcessor:
    @pytest.fixture(scope="class")
    def eicr_processor(self) -> EicrProcessor:
        eicr_path = EXAMPLE_EICRS_DIRECTORY / "basic_test_eicr.xml"
        with eicr_path.open() as f:
            eicr_output = f.read()

        return EicrProcessor(eicr_output)

    @pytest.fixture(scope="class")
    def eicr_metadata(self, eicr_processor: EicrProcessor) -> Metadata:
        return eicr_processor.eicr_metadata

    @pytest.fixture(scope="class")
    def candidates(self, eicr_processor: EicrProcessor) -> list[Candidate]:
        return eicr_processor.get_text_candidates(BASE_XPATH, DataField.LAB_TEST_NAME_RESULTED)

    def test_attribute_candidate(self, candidates: list[Candidate]):
        assert candidates[0] == Candidate(
            value="A custom code in display name.", xpath=LabXPaths.CODE_DISPLAY_NAME
        )

    def test_text_candidate(self, candidates: list[Candidate]):
        assert candidates[1] == Candidate(
            value="A custom code in original text.", xpath=LabXPaths.CODE_ORIGINAL_TEXT
        )

    def test_candidate_count(self, candidates: list[Candidate]):
        expected = 2
        assert len(candidates) == expected

    def test_metadata(self, eicr_metadata: Metadata):
        assert eicr_metadata == Metadata(
            eicr_id=CdaInstanceIdentifier(root="c8516bdc-8bb2-40aa-8dae-20a77546488f"),
            eicr_vendor="Test eCR Vendor Name",
        )

    def test_metadata_raises_when_id_is_missing(self):
        processor = EicrProcessor(
            """
            <ClinicalDocument>
                <author>
                    <assignedAuthor>
                        <assignedAuthoringDevice>
                            <softwareName>Test eCR Vendor Name</softwareName>
                        </assignedAuthoringDevice>
                    </assignedAuthor>
                </author>
            </ClinicalDocument>
            """
        )

        with pytest.raises(ValueError, match=NO_MATCH_FOUND_ERROR_MESSAGE):
            _ = processor.eicr_metadata

    def test_metadata_raises_when_id_has_null_flavor(self):
        processor = EicrProcessor(
            """
            <ClinicalDocument>
                <id nullFlavor="UNK" />
                <author>
                    <assignedAuthor>
                        <assignedAuthoringDevice>
                            <softwareName>Test eCR Vendor Name</softwareName>
                        </assignedAuthoringDevice>
                    </assignedAuthor>
                </author>
            </ClinicalDocument>
            """
        )

        with pytest.raises(ValueError, match=NO_MATCH_FOUND_ERROR_MESSAGE):
            _ = processor.eicr_metadata

    def test_metadata_parses_false_displayable(self):
        processor = EicrProcessor(
            """
            <ClinicalDocument>
                <id
                    root="test-root"
                    extension="test-extension"
                    assigningAuthorityName="test-authority"
                    displayable="false"
                />
                <author>
                    <assignedAuthor>
                        <assignedAuthoringDevice>
                            <softwareName>Test eCR Vendor Name</softwareName>
                        </assignedAuthoringDevice>
                    </assignedAuthor>
                </author>
            </ClinicalDocument>
            """
        )

        assert processor.eicr_metadata == Metadata(
            eicr_id=CdaInstanceIdentifier(
                root="test-root",
                extension="test-extension",
                assigning_authority_name="test-authority",
                displayable=False,
                null_flavor=None,
            ),
            eicr_vendor="Test eCR Vendor Name",
        )

    def test_metadata_parses_unknown_displayable_as_none(self):
        processor = EicrProcessor(
            """
            <ClinicalDocument>
                <id
                    root="test-root"
                    extension="test-extension"
                    assigningAuthorityName="test-authority"
                    displayable="not-a-bool"
                />
                <author>
                    <assignedAuthor>
                        <assignedAuthoringDevice>
                            <softwareName>Test eCR Vendor Name</softwareName>
                        </assignedAuthoringDevice>
                    </assignedAuthor>
                </author>
            </ClinicalDocument>
            """
        )

        assert processor.eicr_metadata == Metadata(
            eicr_id=CdaInstanceIdentifier(
                root="test-root",
                extension="test-extension",
                assigning_authority_name="test-authority",
                displayable=None,
                null_flavor=None,
            ),
            eicr_vendor="Test eCR Vendor Name",
        )

    def test_metadata_parses_true_displayable(self):
        processor = EicrProcessor(
            """
            <ClinicalDocument>
                <id
                    root="test-root"
                    extension="test-extension"
                    assigningAuthorityName="test-authority"
                    displayable="true"
                />
                <author>
                    <assignedAuthor>
                        <assignedAuthoringDevice>
                            <softwareName>Test eCR Vendor Name</softwareName>
                        </assignedAuthoringDevice>
                    </assignedAuthor>
                </author>
            </ClinicalDocument>
            """
        )

        assert processor.eicr_metadata == Metadata(
            eicr_id=CdaInstanceIdentifier(
                root="test-root",
                extension="test-extension",
                assigning_authority_name="test-authority",
                displayable=True,
                null_flavor=None,
            ),
            eicr_vendor="Test eCR Vendor Name",
        )


class TestReferences:
    @pytest.fixture(scope="class")
    def results(self) -> list[Candidate]:
        eicr_path = EXAMPLE_EICRS_DIRECTORY / "reference_test_eicr.xml"
        with eicr_path.open() as f:
            eicr_output = f.read()

        eicr_processor = EicrProcessor(eicr_output)

        return eicr_processor.get_text_candidates(BASE_XPATH, DataField.LAB_TEST_NAME_RESULTED)

    def test_simple_reference(self, results: list[Candidate]):
        expected = "My reference"
        assert Candidate(value=expected, xpath=LabXPaths.CODE_ORIGINAL_TEXT) in results

    def test_additional_text_in_original(self, results: list[Candidate]):
        expected = "This original text has additional text Even more stuff here"
        assert Candidate(value=expected, xpath=LabXPaths.CODE_TRANSLATION_ORIGINAL_TEXT) in results

    def test_additional_text_reference(self, results: list[Candidate]):
        expected = "My reference"
        assert Candidate(value=expected, xpath=LabXPaths.CODE_TRANSLATION_ORIGINAL_TEXT) in results

    def test_complicated_reference(self, results: list[Candidate]):
        expected = "A more complicated reference With extra nodes"
        assert Candidate(value=expected, xpath=LabXPaths.CODE_TRANSLATION_ORIGINAL_TEXT) in results

    def test_row_reference(self, results: list[Candidate]):
        expected = "My reference A more complicated reference With extra nodes"
        assert Candidate(value=expected, xpath=LabXPaths.OBSERVATION_TEXT) in results
