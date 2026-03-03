from collections import defaultdict

from lxml import etree
from lxml.etree import Element
from shared_models import DataField

from text_to_code.models import schematron


def get_data_element_from_schematron_error(schematron_error: str) -> DataField | None:
    """Return the data field that the error message is associated with, if any.

    :param schematron_error: The schematron error message being evaluated.
    :returns: The data field the schematron error is associated with,
        or None if not found.
    """
    for error_enum, data_field in schematron._SCHEMATRON_ENUM_TO_FIELD.items():
        if schematron_error in (e.value for e in error_enum):
            return data_field
    return None


def get_data_fields_from_schematron_error(
    schematron_output: str,
) -> dict[DataField, list[str]]:
    """Find errors that correspond to specific data elements/fields.

    :param schematron_output: The data from the Schematron validation
        run against the eICR document, containing errors that may
        be relevant for TTC processing.
    :returns: Dictionary of Data Field name and list of XPaths of where
        to find data within the eICR for TTC processing.
    """
    if not schematron_output.strip():
        return {}

    xml_root = _create_xml_tree(schematron_output)
    data_fields_with_context = defaultdict(list)

    # Loop through schematron validation results

    for issue in xml_root.findall("failed-assert"):
        try:
            if issue is None:
                continue
            message_elem = issue.find("text")
            context_elem = issue.get("location")
            if message_elem is None or message_elem.text is None or context_elem is None:
                continue
            # Check if message matches any specified schematron errors
            err_data_field = get_data_element_from_schematron_error(message_elem.text)
            if err_data_field is None:
                continue
            xpath = context_elem.replace("Q{urn:hl7-org:v3}", "")
            # Add xpath if not already present (avoiding duplicates)
            if xpath not in data_fields_with_context[err_data_field]:
                data_fields_with_context[err_data_field].append(xpath)

        except Exception as e:
            # TODO: we may want to log this somewhere instead of print
            print(f"Error parsing schematron output: {e}")
            continue
    return data_fields_with_context


def _create_xml_tree(xml: str) -> Element:
    """Remove all namespaces from an XML tree."""
    tree = etree.fromstring(xml.encode("utf-8"))
    for elem in tree.iter():
        if not isinstance(elem.tag, str):
            continue
        elem.tag = etree.QName(elem).localname
    # Remove namespace declarations
    etree.cleanup_namespaces(tree)
    return tree
