from pathlib import Path

import pytest

from dibbs_text_to_code.schemas import eicr
from dibbs_text_to_code.services.eicr_processor import get_text_candidates
from dibbs_text_to_code.services.schematron_processor import get_data_fields_from_schematron_error

current_dir = Path(__file__).parent.parent


class TestGetTextCandidates:
    SCHEMATRON_ERROR_FILE = None
    TEST_EICR_FILE = None

    def file_setup(self) -> None:
        if self.SCHEMATRON_ERROR_FILE is None:
            schematron_path = current_dir / "assets" / "test_schematron_errors.xml"
            with schematron_path.open() as f:
                schematron_output = f.read()
            self.SCHEMATRON_ERROR_FILE = schematron_output

        if self.TEST_EICR_FILE is None:
            eicr_path = current_dir / "assets" / "test_eicr_covid.xml"
            with eicr_path.open() as f:
                eicr_output = f.read()
            self.TEST_EICR_FILE = eicr_output

    def test_get_text_candidates(self) -> None:
        self.file_setup()
        error_result = get_data_fields_from_schematron_error(self.SCHEMATRON_ERROR_FILE)

        expected_num_results = 7
        expected_result = "SARS-like Coronavirus N gene [Presence] in Unspecified specimen by NAA with probe detection"

        xpaths = error_result["Lab Test Name Resulted"][1]

        result = get_text_candidates(
            self.TEST_EICR_FILE, xpaths, eicr.EicrDataField.LAB_TEST_NAME_RESULTED
        )

        assert len(result) == expected_num_results
        assert (
            result[
                "/ClinicalDocument/component[1]/structuredBody[1]/component[6]/section[1]/entry[1]/organizer[1]/component[1]/observation[1]/code/@displayName[0]"
            ]
            == expected_result
        )
        assert (
            result[
                "/ClinicalDocument/component[1]/structuredBody[1]/component[6]/section[1]/entry[1]/organizer[1]/component[1]/observation[1]/code/translation/originalText[0]"
            ]
            == "COVID-19 Spike IgG"
        )

    def test_text_candidates_wrong_datatype(self) -> None:
        self.file_setup()
        error_result = get_data_fields_from_schematron_error(self.SCHEMATRON_ERROR_FILE)

        xpath = error_result[eicr.EicrDataField.LAB_TEST_NAME_RESULTED][1]

        with pytest.raises(KeyError):
            get_text_candidates(self.TEST_EICR_FILE, xpath, "invalid_field")

    def test_get_text_candidates_empty_ecr(self) -> None:
        self.file_setup()
        error_result = get_data_fields_from_schematron_error(self.SCHEMATRON_ERROR_FILE)

        xpath = error_result[eicr.EicrDataField.LAB_TEST_NAME_RESULTED][1]
        result = get_text_candidates("", xpath, eicr.EicrDataField.LAB_TEST_NAME_RESULTED)
        assert len(result) == 0


class TestGetTextCandidatesReferences:
    @pytest.fixture(scope="class")
    def results(self) -> dict[str, str]:
        eicr_path = current_dir / "assets" / "reference_test_eicr.xml"
        with eicr_path.open() as f:
            eicr_output = f.read()

        xpath = "/ClinicalDocument/component/structuredBody/component/section/entry/component/observation"

        return get_text_candidates(eicr_output, xpath, "lab_result")

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
