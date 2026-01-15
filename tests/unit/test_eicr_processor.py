from pathlib import Path

import pytest

from dibbs_text_to_code.models import Candidate
from dibbs_text_to_code.services.eicr_processor import EicrProcessor

EXAMPLE_EICRS_DIRECTORY = Path(__file__).parent.parent / "assets"

BASE_XPATH = (
    "/ClinicalDocument/component/structuredBody/component/section/entry/component/observation"
)


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
    def result(self) -> list[Candidate]:
        eicr_path = EXAMPLE_EICRS_DIRECTORY / "basic_test_eicr.xml"
        with eicr_path.open() as f:
            eicr_output = f.read()

        return EicrProcessor(eicr_output).get_text_candidates(BASE_XPATH, "lab_result")

    def test_attribute_candidate(self, result: list[Candidate]) -> None:
        full_xpath = f"/{BASE_XPATH}/code/@displayName[0]"

        assert result[0] == Candidate(value="A custom code in display name.", xpath=full_xpath)

    def test_text_candidate(self, result: list[Candidate]) -> None:
        full_xpath = f"/{BASE_XPATH}/code/originalText[0]"

        assert result[1] == Candidate(value="A custom code in original text.", xpath=full_xpath)

    def test_candidate_count(self, result: list[Candidate]) -> None:
        expected = 2
        assert len(result) == expected


class TestReferences:
    @pytest.fixture(scope="class")
    def results(self) -> list[Candidate]:
        eicr_path = EXAMPLE_EICRS_DIRECTORY / "reference_test_eicr.xml"
        with eicr_path.open() as f:
            eicr_output = f.read()

        eicr_processor = EicrProcessor(eicr_output)

        return eicr_processor.get_text_candidates(BASE_XPATH, "lab_result")

    def test_simple_reference(self, results: list[Candidate]) -> None:
        full_xpath = f"/{BASE_XPATH}/code/originalText[0]"
        expected = "My reference"
        assert results[0] == Candidate(value=expected, xpath=full_xpath)

    def test_additional_text_in_original(self, results: list[Candidate]) -> None:
        full_xpath = f"/{BASE_XPATH}/code/translation/originalText[0]"
        expected = "This original text has additional text My reference Even more stuff here"
        assert results[1] == Candidate(value=expected, xpath=full_xpath)

    def test_complicated_reference(self, results: list[Candidate]) -> None:
        full_xpath = f"/{BASE_XPATH}/code/translation/originalText[1]"
        expected = "A more complicated reference With extra nodes"
        assert results[2] == Candidate(value=expected, xpath=full_xpath)
