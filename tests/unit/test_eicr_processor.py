from pathlib import Path

import pytest

from dibbs_text_to_code.services.eicr_processor import EicrProcessor

EXAMPLE_EICRS_DIRECTORY = Path(__file__).parent.parent / "assets"


class TestEicrProcessor:
    @pytest.fixture(scope="class")
    def covid_eicr(self) -> EicrProcessor:
        eicr_path = EXAMPLE_EICRS_DIRECTORY / "test_eicr_covid.xml"
        with eicr_path.open() as f:
            eicr_output = f.read()

        return EicrProcessor(eicr_output)

    @pytest.fixture(scope="class")
    def references_test_eicr(self) -> EicrProcessor:
        eicr_path = EXAMPLE_EICRS_DIRECTORY / "reference_test_eicr.xml"
        with eicr_path.open() as f:
            eicr_output = f.read()

        return EicrProcessor(eicr_output)

    def test_init(self) -> None:
        """Test initialization of an EICR processor.

        This feels like a silly unit test as an EICR processor does not have any public attributes,
        but IDK initialization may become more complicated.
        """
        assert EicrProcessor("<tag />")

    def test_get_text_candidates_empty_xpath(self, covid_eicr: EicrProcessor) -> None:
        result = covid_eicr.get_text_candidates("", "lab_result")
        assert len(result) == 0
