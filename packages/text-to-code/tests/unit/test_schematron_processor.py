from pathlib import Path

from shared_models import DataField
from text_to_code.services.schematron_processor import get_data_fields_from_schematron_error

current_dir = Path(__file__).parent.parent


class TestSchematronProcessor:
    SCHEMATRON_ERROR_FILE = None

    def file_setup(self) -> None:
        if self.SCHEMATRON_ERROR_FILE is None:
            schematron_path = current_dir / "assets" / "test_schematron_errors.xml"
            with schematron_path.open() as f:
                schematron_output = f.read()
            self.SCHEMATRON_ERROR_FILE = schematron_output

    def test_get_schematron_error_data_fields(self):
        self.file_setup()
        error_result = get_data_fields_from_schematron_error(
            self.SCHEMATRON_ERROR_FILE,
        )

        expected_lab_test_name_resulted = 2
        expected_lab_test_name_ordered = 2

        lab_test_name_resulted_errors = [
            error for error in error_result if error.field == DataField.LAB_TEST_NAME_RESULTED
        ]
        lab_test_name_ordered_errors = [
            error for error in error_result if error.field == DataField.LAB_TEST_NAME_ORDERED
        ]

        assert len(lab_test_name_resulted_errors) == expected_lab_test_name_resulted
        assert len(lab_test_name_ordered_errors) == expected_lab_test_name_ordered

    def test_get_schematron_error_empty_xml(self):
        schematron_errors = ""
        result = get_data_fields_from_schematron_error(schematron_errors)

        assert result == []
