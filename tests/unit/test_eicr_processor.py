from pathlib import Path

import pytest

from dibbs_text_to_code.services.eicr_processor import EicrProcessor

EXAMPLE_EICRS_DIRECTORY = Path(__file__).parent.parent / "assets"


class TestEmptyEicrProcessor:
    def test_init(self) -> None:
        """Test initialization of an EICR processor.

        This feels like a silly unit test as an EICR processor does not have any public attributes,
        but IDK initialization may become more complicated.
        """
        assert EicrProcessor("<tag />")

    def test_get_text_candidates_empty_xpath(self) -> None:
        result = EicrProcessor("<tag />").get_text_candidates("", "lab_result")
        assert len(result) == 0


class TestBasicEicrProcessor:
    @pytest.fixture(scope="class")
    def result(self) -> EicrProcessor:
        eicr_path = EXAMPLE_EICRS_DIRECTORY / "basic_test_eicr.xml"
        with eicr_path.open() as f:
            eicr_output = f.read()

        base_xpath = "/ClinicalDocument/component/structuredBody/component/section/entry/component/observation"
        return EicrProcessor(eicr_output).get_text_candidates(base_xpath, "lab_result")

    def test_attribute_candidate(self, result: dict[str, str]) -> None:
        key = "/ClinicalDocument/component/structuredBody/component/section/entry/component/observation/code/@displayName[0]"

        assert result[key] == "A custom code in display name."

    def test_text_candidate(self, result: dict[str, str]) -> None:
        key = "/ClinicalDocument/component/structuredBody/component/section/entry/component/observation/code/originalText[0]"

        assert result[key] == "A custom code in original text."

    def test_candidate_count(self, result: dict[str, str]) -> None:
        expected = 2
        assert len(result) == expected


class TestReferences:
    @pytest.fixture(scope="class")
    def results(self) -> dict[str, str]:
        eicr_path = EXAMPLE_EICRS_DIRECTORY / "reference_test_eicr.xml"
        with eicr_path.open() as f:
            eicr_output = f.read()

        eicr_processor = EicrProcessor(eicr_output)
        xpath = "/ClinicalDocument/component/structuredBody/component/section/entry/component/observation"

        return eicr_processor.get_text_candidates(xpath, "lab_result")

    def test_simple_reference(self, results: dict[str, str]) -> None:
        key = "/ClinicalDocument/component/structuredBody/component/section/entry/component/observation/code/originalText[0]"
        expected = "My reference"
        assert results[key] == expected

    def test_additional_text_in_original(self, results: dict[str, str]) -> None:
        key = "/ClinicalDocument/component/structuredBody/component/section/entry/component/observation/code/translation/originalText[0]"
        expected = "This original text has additional text My reference Even more stuff here"
        assert results[key] == expected

    def test_complicated_reference(self, results: dict[str, str]) -> None:
        key = "/ClinicalDocument/component/structuredBody/component/section/entry/component/observation/code/translation/originalText[1]"
        expected = "A more complicated reference With extra nodes"
        assert results[key] == expected
