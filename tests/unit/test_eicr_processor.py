from pathlib import Path

from dibbs_text_to_code.services.eicr_processor import _enhance_xpath_with_namespace
from dibbs_text_to_code.services.eicr_processor import get_text_candidates

current_dir = Path(__file__).parent.parent


class TestEICRProcessor:
    TEST_EICR_FILE = None

    def file_setup(self) -> None:
        if self.TEST_EICR_FILE is None:
            eicr_path = current_dir / "assets" / "test_eicr_covid.xml"
            with eicr_path.open() as f:
                eicr_output = f.read()
            self.TEST_EICR_FILE = eicr_output

    def test_get_text_candidates_empty_xpath(self) -> None:
        self.file_setup()

        result = get_text_candidates(self.TEST_EICR_FILE, "", "lab_result")
        assert len(result) == 0

    def test_enhance_xpath_with_namespace(self) -> None:
        base_xpath = "/component/structuredBody/component/section/entry/observation/value"
        expected_xpath = (
            "./cda:component/cda:structuredBody/cda:component/cda:section/cda:entry/"
            "cda:observation/cda:value"
        )

        result = _enhance_xpath_with_namespace(base_xpath, "cda")
        assert result == expected_xpath

        base_xpath = "/component/structuredBody/component/section/entry/observation/code/@code"
        expected_xpath = (
            "./cda:component/cda:structuredBody/cda:component/cda:section/cda:entry/"
            "cda:observation/cda:code/@code"
        )

        result = _enhance_xpath_with_namespace(base_xpath, "cda")
        assert result == expected_xpath

        base_xpath = (
            "/component/structuredBody/component/section/entry/observation/code/originalText/text()"
        )
        expected_xpath = (
            "./cda:component/cda:structuredBody/cda:component/cda:section/cda:entry/"
            "cda:observation/cda:code/cda:originalText/text()"
        )

        result = _enhance_xpath_with_namespace(base_xpath, "cda")
        assert result == expected_xpath
