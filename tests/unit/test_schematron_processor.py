from pathlib import Path

from dibbs_text_to_code.services.schematron_processor import get_data_fields_from_schematron_error

current_dir = Path(__file__).parent.parent


class TestSchematronProcessor:
    SCHEMATRON_ERROR_FILE = None

    def file_setup(self) -> None:
        if self.SCHEMATRON_ERROR_FILE is None:
            schematron_path = current_dir / "assets" / "test_schematron_errors.xml"
            with schematron_path.open() as f:
                schematron_output = f.read()
            self.SCHEMATRON_ERROR_FILE = schematron_output

    def test_get_schematron_error_data_fields(self) -> None:
        self.file_setup()
        error_result = get_data_fields_from_schematron_error(
            self.SCHEMATRON_ERROR_FILE,
        )

        expected_lab_results = 2
        expected_lab_orders = 1

        assert len(error_result["lab_result"]) == expected_lab_results
        assert len(error_result["lab_order"]) == expected_lab_orders

    def test_get_schematron_error_empty_xml(self) -> None:
        schematron_errors = ""
        result = get_data_fields_from_schematron_error(schematron_errors)

        assert result == {}
