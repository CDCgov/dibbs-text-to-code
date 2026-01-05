from pathlib import Path

from services import eicr_processor

current_dir = Path(__file__).parent


class TestEICRProcessor:  # noqa: D101
    def get_schematron_output_file(self):
        schematron_path = current_dir / "assets" / "test_schematron_errors.xml"
        with open(schematron_path, "r", encoding="utf-8") as f:
            schematron_output = f.read()
        return schematron_output

    def get_test_eicr_file(self):
        eicr_path = current_dir / "assets" / "test_eicr_covid.xml"
        with open(eicr_path, "r", encoding="utf-8") as f:
            eicr_output = f.read()
        return eicr_output

    def test_get_schematron_error_data_fields(self):
        schematron_errors = self.get_schematron_output_file()
        error_result = eicr_processor.get_data_fields_from_schematron_error(schematron_errors)

        assert error_result != {}
        print(f"Error Result: {error_result}")
        assert "lab_result" in error_result
        assert len(error_result["lab_result"]) == 2
        assert "lab_order" in error_result
        assert len(error_result["lab_order"]) == 1

    def test_get_text_candidates(self):
        schematron_errors = self.get_schematron_output_file()
        eicr_xml = self.get_test_eicr_file()
        error_result = eicr_processor.get_data_fields_from_schematron_error(schematron_errors)

        xpaths = error_result["lab_result"][1]
        result = eicr_processor.get_text_candidates(eicr_xml, xpaths, "lab_result")
        assert len(result) == 7
        assert (
            result[0]
            == "SARS-like Coronavirus N gene [Presence] in Unspecified specimen by NAA with probe detection"
        )
        assert result[6] == "SARS-like Virus"

    def test_get_schematron_error_empty_xml(self):
        schematron_errors = ""
        result = eicr_processor.get_data_fields_from_schematron_error(schematron_errors)

        assert result == {}

    def test_get_text_candidates_empty_ecr(self):
        schematron_errors = self.get_schematron_output_file()
        error_result = eicr_processor.get_data_fields_from_schematron_error(schematron_errors)

        xpath = error_result["lab_result"][1]
        result = eicr_processor.get_text_candidates("", xpath, "lab_result")
        assert len(result) == 0

    def test_get_text_candidates_empty_xpath(self):
        eicr_xml = self.get_test_eicr_file()

        result = eicr_processor.get_text_candidates(eicr_xml, "", "lab_result")
        assert len(result) == 0

    def test_text_candidates_wrong_datatype(self):
        eicr_xml = self.get_test_eicr_file()
        schematron_errors = self.get_schematron_output_file()
        error_result = eicr_processor.get_data_fields_from_schematron_error(schematron_errors)

        xpath = error_result["lab_result"][1]

        result = eicr_processor.get_text_candidates(eicr_xml, xpath, "my_field")
        assert len(result) == 0
