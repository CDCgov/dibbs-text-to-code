from pathlib import Path

from services import eicr_processor

current_dir = Path(__file__).parent


class TestEICRProcessor:  # noqa: D101
    SCHEMATRON_ERROR_FILE = None
    TEST_EICR_FILE = None

    def file_setup(self):
        if self.SCHEMATRON_ERROR_FILE is None:
            schematron_path = current_dir / "assets" / "test_schematron_errors.xml"
            with open(schematron_path, "r", encoding="utf-8") as f:
                schematron_output = f.read()
            self.SCHEMATRON_ERROR_FILE = schematron_output

        if self.TEST_EICR_FILE is None:
            eicr_path = current_dir / "assets" / "test_eicr_covid.xml"
            with open(eicr_path, "r", encoding="utf-8") as f:
                eicr_output = f.read()
            self.TEST_EICR_FILE = eicr_output

    def test_get_schematron_error_data_fields(self):
        self.file_setup()
        error_result = eicr_processor.get_data_fields_from_schematron_error(
            self.SCHEMATRON_ERROR_FILE
        )

        assert error_result != {}
        assert "lab_result" in error_result
        assert len(error_result["lab_result"]) == 2
        assert "lab_order" in error_result
        assert len(error_result["lab_order"]) == 1

    def test_get_text_candidates(self):
        self.file_setup()
        error_result = eicr_processor.get_data_fields_from_schematron_error(
            self.SCHEMATRON_ERROR_FILE
        )

        xpaths = error_result["lab_result"][1]
        result = eicr_processor.get_text_candidates(self.TEST_EICR_FILE, xpaths, "lab_result")
        assert len(result) == 7
        count = 0
        for key, value in result.items():
            if count == 0:
                assert (
                    value
                    == "SARS-like Coronavirus N gene [Presence] in Unspecified specimen by NAA with probe detection"
                )
            if count == 6:
                assert value == "SARS-like Virus"
            count += 1

    def test_get_schematron_error_empty_xml(self):
        schematron_errors = ""
        result = eicr_processor.get_data_fields_from_schematron_error(schematron_errors)

        assert result == {}

    def test_get_text_candidates_empty_ecr(self):
        self.file_setup()
        error_result = eicr_processor.get_data_fields_from_schematron_error(
            self.SCHEMATRON_ERROR_FILE
        )

        xpath = error_result["lab_result"][1]
        result = eicr_processor.get_text_candidates("", xpath, "lab_result")
        assert len(result) == 0

    def test_get_text_candidates_empty_xpath(self):
        self.file_setup()

        result = eicr_processor.get_text_candidates(self.TEST_EICR_FILE, "", "lab_result")
        assert len(result) == 0

    def test_text_candidates_wrong_datatype(self):
        self.file_setup()
        error_result = eicr_processor.get_data_fields_from_schematron_error(
            self.SCHEMATRON_ERROR_FILE
        )

        xpath = error_result["lab_result"][1]

        result = eicr_processor.get_text_candidates(self.TEST_EICR_FILE, xpath, "my_field")
        assert len(result) == 0

    def test_enhance_xpath_with_namespace(self):
        base_xpath = "/component/structuredBody/component/section/entry/observation/value"
        expected_xpath = (
            "./cda:component/cda:structuredBody/cda:component/cda:section/cda:entry/"
            "cda:observation/cda:value"
        )

        result = eicr_processor._enhance_xpath_with_namespace(base_xpath, "cda")
        assert result == expected_xpath

        base_xpath = "/component/structuredBody/component/section/entry/observation/code/@code"
        expected_xpath = (
            "./cda:component/cda:structuredBody/cda:component/cda:section/cda:entry/"
            "cda:observation/cda:code/@code"
        )

        result = eicr_processor._enhance_xpath_with_namespace(base_xpath, "cda")
        assert result == expected_xpath

        base_xpath = (
            "/component/structuredBody/component/section/entry/observation/code/originalText/text()"
        )
        expected_xpath = (
            "./cda:component/cda:structuredBody/cda:component/cda:section/cda:entry/"
            "cda:observation/cda:code/cda:originalText/text()"
        )

        result = eicr_processor._enhance_xpath_with_namespace(base_xpath, "cda")
        assert result == expected_xpath
