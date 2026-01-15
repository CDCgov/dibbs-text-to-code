from pathlib import Path

from lxml import etree

from dibbs_text_to_code.services.eicr_processor import _enhance_xpath_with_namespace
from dibbs_text_to_code.services.eicr_processor import get_text_candidates
from dibbs_text_to_code.services.eicr_processor import resolve_reference

CURRENT_DIR = Path(__file__).parent.parent


class TestEICRProcessor:
    TEST_EICR_FILE = None

    def file_setup(self) -> None:
        if self.TEST_EICR_FILE is None:
            eicr_path = CURRENT_DIR / "assets" / "test_eicr_covid.xml"
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

    def test_get_reference_value(self) -> None:
        eicr_path = CURRENT_DIR / "assets" / "reference_test_eicr.xml"
        with eicr_path.open() as eicr_file:
            eicr_string = eicr_file.read()

        xml_root = etree.fromstring(eicr_string.encode("utf-8"))

        expected = "My reference"
        actual = resolve_reference(xml_root, "#simple_reference_1")

        assert actual == expected

    def test_resolve_reference_not_found(self) -> None:
        eicr_path = CURRENT_DIR / "assets" / "reference_test_eicr.xml"
        with eicr_path.open() as eicr_file:
            eicr_string = eicr_file.read()

        xml_root = etree.fromstring(eicr_string.encode("utf-8"))

        actual = resolve_reference(
            xml_root,
            "#Result.1.2.840.114350.1.13.478.3.7.2.798268.2047881.Comp3Name",
        )

        assert actual is None

    def test_resolve_reference_additional_nodes_in_reference(self) -> None:
        eicr_path = CURRENT_DIR / "assets" / "reference_test_eicr.xml"
        with eicr_path.open() as eicr_file:
            eicr_string = eicr_file.read()

        xml_root = etree.fromstring(eicr_string.encode("utf-8"))
        expected = "A more complicated reference With extra nodes"
        actual = resolve_reference(xml_root, "#complicated_reference_1")

        assert actual == expected
