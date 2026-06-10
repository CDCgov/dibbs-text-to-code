from pathlib import Path
from unittest.mock import patch

from lxml import etree

from shared_models import CdaInstanceIdentifier, DataField
from text_to_code.services.schematron_processor import (
    _get_eicr_id,
    _get_error_enum_value,
    get_data_element_from_schematron_error,
    get_data_fields_from_schematron_error,
)

current_dir = Path(__file__).parent.parent


class TestSchematronProcessor:
    SCHEMATRON_ERROR_FILE: str | None = None

    def file_setup(self) -> str:
        if self.SCHEMATRON_ERROR_FILE is None:
            schematron_path = current_dir / "assets" / "test_schematron_errors.xml"
            with schematron_path.open() as f:
                schematron_output = f.read()
            self.SCHEMATRON_ERROR_FILE = schematron_output

        return self.SCHEMATRON_ERROR_FILE

    def test_get_data_element_from_schematron_error_returns_none_for_unknown_message(self):
        result = get_data_element_from_schematron_error("unknown schematron error")

        assert result is None

    def test_get_error_enum_value_returns_none_for_unknown_message(self):
        result = _get_error_enum_value("unknown schematron error")

        assert result is None

    def test_get_eicr_id_returns_none_when_id_missing(self):
        xml_root = etree.fromstring("<ClinicalDocument />")

        result = _get_eicr_id(xml_root)

        assert result is None

    def test_get_eicr_id_returns_none_when_root_missing(self):
        xml_root = etree.fromstring("<ClinicalDocument><id extension='abc' /></ClinicalDocument>")

        result = _get_eicr_id(xml_root)

        assert result is None

    def test_get_eicr_id_returns_identifier_when_present(self):
        xml_root = etree.fromstring(
            "<ClinicalDocument><id root='test-root' extension='test-extension' /></ClinicalDocument>"
        )

        result = _get_eicr_id(xml_root)

        assert result == CdaInstanceIdentifier(root="test-root", extension="test-extension")

    def test_get_schematron_error_data_fields(self):
        schematron_error_file = self.file_setup()
        error_result = get_data_fields_from_schematron_error(
            schematron_error_file,
        )

        expected_lab_test_name_resulted = 2
        expected_lab_test_name_ordered = 2

        lab_test_name_resulted_errors = [
            error for error in error_result if error.field == DataField.LAB_TEST_NAME_RESULTED
        ]
        print(f"HERE: {lab_test_name_resulted_errors}")
        lab_test_name_ordered_errors = [
            error for error in error_result if error.field == DataField.LAB_TEST_NAME_ORDERED
        ]
        print(f"HERE2: {lab_test_name_ordered_errors}")

        assert len(lab_test_name_resulted_errors) == expected_lab_test_name_resulted
        assert len(lab_test_name_ordered_errors) == expected_lab_test_name_ordered

    def test_get_schematron_error_detail_fields(self):
        schematron_error_file = self.file_setup()
        error_result = get_data_fields_from_schematron_error(
            schematron_error_file,
        )
        expected_total_errors = 4

        assert len(error_result) == expected_total_errors

        lab_test_name_resulted_error = next(
            error
            for error in error_result
            if error.field == DataField.LAB_TEST_NAME_RESULTED
            and error.error_message
            == "Text to Code: Lab Test Name Resulted does not have a @code attribute."
        )

        assert lab_test_name_resulted_error.eicr_id is None
        assert lab_test_name_resulted_error.field == DataField.LAB_TEST_NAME_RESULTED
        assert (
            lab_test_name_resulted_error.error
            == "Text to Code: Lab Test Name Resulted does not have a @code attribute."
        )
        assert (
            lab_test_name_resulted_error.error_message
            == "Text to Code: Lab Test Name Resulted does not have a @code attribute."
        )
        assert (
            lab_test_name_resulted_error.error_context
            == "/ClinicalDocument/component[1]/structuredBody[1]/component[5]/section[1]/entry[1]/organizer[1]/component[1]/observation[1]"
        )
        assert (
            lab_test_name_resulted_error.error_test
            == "not(cda:code) or cda:code/@code or cda:code/cda:translation/@code"
        )
        assert lab_test_name_resulted_error.error_id is None
        assert lab_test_name_resulted_error.candidate is None

    def test_get_schematron_error_empty_xml(self):
        schematron_errors = ""
        result = get_data_fields_from_schematron_error(schematron_errors)

        assert result == []

    def test_get_schematron_error_processes_validation_result_root(self):
        schematron_errors = """
        <validationResult>
            <issue>
                <message>Text to Code: Lab Test Name Resulted does not have a @code attribute.</message>
                <context>/ClinicalDocument/component[1]</context>
                <test>test-expression</test>
                <assertionID>ttc-labTestNameResulted-code-missing</assertionID>
            </issue>
        </validationResult>
        """

        result = get_data_fields_from_schematron_error(schematron_errors)

        assert len(result) == 1
        assert result[0].field == DataField.LAB_TEST_NAME_RESULTED
        assert (
            result[0].error
            == "Text to Code: Lab Test Name Resulted does not have a @code attribute."
        )
        assert (
            result[0].error_message
            == "Text to Code: Lab Test Name Resulted does not have a @code attribute."
        )
        assert result[0].error_context == "/ClinicalDocument/component[1]"
        assert result[0].error_test == "test-expression"
        assert result[0].error_id == "ttc-labTestNameResulted-code-missing"
        assert result[0].candidate is None

    def test_get_schematron_error_skips_validation_result_when_issue_is_missing(self):
        schematron_errors = """
        <root>
            <result>
                <validationResult />
            </result>
        </root>
        """

        result = get_data_fields_from_schematron_error(schematron_errors)

        assert result == []

    def test_get_schematron_error_skips_validation_result_when_message_is_missing(self):
        schematron_errors = """
        <root>
            <result>
                <validationResult>
                    <issue>
                        <context>/ClinicalDocument/component[1]</context>
                    </issue>
                </validationResult>
            </result>
        </root>
        """

        result = get_data_fields_from_schematron_error(schematron_errors)

        assert result == []

    def test_get_schematron_error_skips_validation_result_when_context_is_missing(self):
        schematron_errors = """
        <root>
            <result>
                <validationResult>
                    <issue>
                        <message>Text to Code: Lab Test Name Resulted does not have a @code attribute.</message>
                    </issue>
                </validationResult>
            </result>
        </root>
        """

        result = get_data_fields_from_schematron_error(schematron_errors)

        assert result == []

    def test_get_schematron_error_skips_when_message_has_no_matching_data_field(self):
        schematron_errors = """
        <root>
            <result>
                <validationResult>
                    <issue>
                        <message>unknown schematron error</message>
                        <context>/ClinicalDocument/component[1]</context>
                    </issue>
                </validationResult>
            </result>
        </root>
        """

        result = get_data_fields_from_schematron_error(schematron_errors)

        assert result == []

    def test_get_schematron_error_skips_when_error_enum_value_is_none(self):
        schematron_errors = """
        <root>
            <result>
                <validationResult>
                    <issue>
                        <message>Text to Code: Lab Test Name Resulted does not have a @code attribute.</message>
                        <context>/ClinicalDocument/component[1]</context>
                    </issue>
                </validationResult>
            </result>
        </root>
        """

        with (
            patch(
                "text_to_code.services.schematron_processor.get_data_element_from_schematron_error",
                return_value=DataField.LAB_TEST_NAME_RESULTED,
            ),
            patch(
                "text_to_code.services.schematron_processor._get_error_enum_value",
                return_value=None,
            ),
        ):
            result = get_data_fields_from_schematron_error(schematron_errors)

        assert result == []

    def test_get_schematron_error_deduplicates_duplicate_errors(self):
        schematron_errors = """
        <root>
            <result>
                <validationResult>
                    <issue>
                        <message>Text to Code: Lab Test Name Resulted does not have a @code attribute.</message>
                        <context>/ClinicalDocument/component[1]</context>
                        <test>test-expression</test>
                    </issue>
                </validationResult>
                <validationResult>
                    <issue>
                        <message>Text to Code: Lab Test Name Resulted does not have a @code attribute.</message>
                        <context>/ClinicalDocument/component[1]</context>
                        <test>test-expression</test>
                    </issue>
                </validationResult>
            </result>
        </root>
        """

        result = get_data_fields_from_schematron_error(schematron_errors)

        assert len(result) == 1

    def test_get_schematron_error_logs_when_issue_processing_fails(self):
        schematron_errors = """
        <root>
            <result>
                <validationResult>
                    <issue>
                        <message>Text to Code: Lab Test Name Resulted does not have a @code attribute.</message>
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
            extra={
                "error_message": "Text to Code: Lab Test Name Resulted does not have a @code attribute.",
                "error_context": "/ClinicalDocument/component[1]/structuredBody[1]/component[5]/section[1]/entry[1]/organizer[1]/component[1]/observation[1]",
                "status": "error",
            },
        )
