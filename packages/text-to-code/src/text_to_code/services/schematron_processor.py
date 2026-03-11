from collections import defaultdict

from lxml import etree
from shared_models import DataField

from text_to_code.models.schematron import _SCHEMATRON_ENUM_TO_FIELD
from text_to_code.models.schematron import DataFieldSchematronErrors
from text_to_code.models.schematron import SchematronErrorDetail
from text_to_code.models.schematron import SchematronErrorReport


def get_data_element_from_schematron_error(schematron_error: str) -> DataField | None:
    """Return the data field that the error message is associated with, if any.

    :param schematron_error: The schematron error message being evaluated.
    :returns: The data field the schematron error is associated with,
        or None if not found.
    """
    for error_enum, data_field in _SCHEMATRON_ENUM_TO_FIELD.items():
        if schematron_error in (e.value for e in error_enum):
            return data_field
    return None


def get_data_fields_from_schematron_error(
    schematron_output: str,
) -> SchematronErrorReport:
    """Find errors that correspond to specific data elements/fields.

    :param schematron_output: The data from the Schematron validation
        run against the eICR document, containing errors that may
        be relevant for TTC processing.
    :returns: Structured report of Data Fields and associated
        Schematron error details for TTC processing.
    """
    if not schematron_output.strip():
        return SchematronErrorReport(data_fields=[])

    xml_root = etree.fromstring(schematron_output.encode("utf-8"))
    data_fields_with_context: defaultdict[DataField, list[SchematronErrorDetail]] = defaultdict(
        list
    )

    # Loop through schematron validation results
    for result in xml_root:
        for vr in result.findall("validationResult"):
            try:
                issue = vr.find("issue")
                if issue is None:
                    continue
                message_elem = issue.find("message")
                context_elem = issue.find("context")
                test_elem = issue.find("test")
                id_elem = issue.find("id")
                if (
                    message_elem is None
                    or message_elem.text is None
                    or context_elem is None
                    or context_elem.text is None
                ):
                    continue
                # Check if message matches any specified schematron errors
                err_data_field = get_data_element_from_schematron_error(message_elem.text)
                if err_data_field is None:
                    continue
                error_detail = SchematronErrorDetail(
                    error_message=message_elem.text,
                    error_context=context_elem.text,
                    error_test=test_elem.text if test_elem is not None else vr.get("test"),
                    error_id=(
                        id_elem.text
                        if id_elem is not None and id_elem.text is not None
                        else vr.get("id") or issue.get("id")
                    ),
                )
                if error_detail not in data_fields_with_context[err_data_field]:
                    data_fields_with_context[err_data_field].append(error_detail)
            except Exception as e:
                # TODO: we may want to log this somewhere instead of print
                print(f"Error parsing schematron output: {e}")
                continue

    return SchematronErrorReport(
        data_fields=[
            DataFieldSchematronErrors(data_field=data_field, errors=errors)
            for data_field, errors in data_fields_with_context.items()
        ]
    )
