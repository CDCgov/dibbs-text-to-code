from pathlib import Path

from dibbs_text_to_code.schemas import eicr
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

        expected_lab_test_name_resulted = 2
        expected_lab_test_name_ordered = 1

        assert (
            len(error_result[eicr.EicrDataField.LAB_TEST_NAME_RESULTED])
            == expected_lab_test_name_resulted
        )
        assert (
            len(error_result[eicr.EicrDataField.LAB_TEST_NAME_ORDERED])
            == expected_lab_test_name_ordered
        )

    def test_get_schematron_error_empty_xml(self) -> None:
        schematron_errors = ""
        result = get_data_fields_from_schematron_error(schematron_errors)

        assert result == {}
