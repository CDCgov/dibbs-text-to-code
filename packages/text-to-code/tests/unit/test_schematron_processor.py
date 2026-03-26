from pathlib import Path
from unittest.mock import patch

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

    def test_get_schematron_error_detail_fields(self):
        self.file_setup()
        error_result = get_data_fields_from_schematron_error(
            self.SCHEMATRON_ERROR_FILE,
        )

        expected_total_errors = 4

        assert len(error_result) == expected_total_errors

        lab_test_name_resulted_error = next(
            error
            for error in error_result
            if error.field == DataField.LAB_TEST_NAME_RESULTED
            and error.error_message
            == "Text to Code: Lab Test Name Resulted does not have a @code attribute"
        )

        assert lab_test_name_resulted_error.eicr_id is None
        assert lab_test_name_resulted_error.field == DataField.LAB_TEST_NAME_RESULTED
        assert (
            lab_test_name_resulted_error.error
            == "Text to Code: Lab Test Name Resulted does not have a @code attribute"
        )
        assert (
            lab_test_name_resulted_error.error_message
            == "Text to Code: Lab Test Name Resulted does not have a @code attribute"
        )
        assert (
            lab_test_name_resulted_error.error_context
            == "/ClinicalDocument/component[1]/structuredBody[1]/component[5]/section[1]/entry[1]/organizer[1]/component[1]/observation[1]"
        )
        assert (
            lab_test_name_resulted_error.error_test
            == " not(cda:code) or cda:code/@code or cda:code/cda:translation/@code"
        )
        assert lab_test_name_resulted_error.error_id is None
        assert lab_test_name_resulted_error.candidate is None

    def test_get_schematron_error_empty_xml(self):
        schematron_errors = ""
        result = get_data_fields_from_schematron_error(schematron_errors)

        assert result == []

    def test_get_schematron_error_logs_when_issue_processing_fails(self):
        schematron_errors = """
        <root>
            <result>
                <validationResult>
                    <issue>
                        <message>Text to Code: Lab Test Name Resulted does not have a @code attribute</message>
                        <context>/ClinicalDocument/component[1]/structuredBody[1]/component[5]/section[1]/entry[1]/organizer[1]/component[1]/observation[1]</context>
                        <test>not(cda:code) or cda:code/@code or cda:code/cda:translation/@code</test>
                    </issue>
                </validationResult>
            </result>
        </root>
        """

        with (
            patch(
                "text_to_code.services.schematron_processor.get_data_element_from_schematron_error",
                side_effect=Exception("boom"),
            ),
            patch("text_to_code.services.schematron_processor.logger.exception") as mock_exception,
        ):
            result = get_data_fields_from_schematron_error(schematron_errors)

        assert result == []
        mock_exception.assert_called_once_with(
            "Failed to process a schematron error detail",
            error_message="Text to Code: Lab Test Name Resulted does not have a @code attribute",
            error_context="/ClinicalDocument/component[1]/structuredBody[1]/component[5]/section[1]/entry[1]/organizer[1]/component[1]/observation[1]",
        )
