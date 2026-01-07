from collections import defaultdict

from configs.general import get_configuration_for_data_element
from configs.general import get_data_element_from_schematron_error
from lxml import etree

NAMESPACES = {
    "cda": "urn:hl7-org:v3",
    "sdtc": "urn:hl7-org:sdtc",
    "voc": "http://www.lantanagroup.com/voc",
    "xsi": "http://www.w3.org/2001/XMLSchema-instance",
}


def get_data_fields_from_schematron_error(schematron_output: str) -> dict:
    """Find errors that correspond to specific data elements/fields.

    :param schematron_output: The data from the Schematron validation
        run against the eICR document, containing errors that may
        be relevant for TTC processing.
    :returns: Dictionary of Data Field name and list of XPaths of where
        to find data within the eICR for TTC processing.
    """
    if not schematron_output.strip():
        return {}

    xml_root = etree.fromstring(schematron_output.encode("utf-8"))
    data_fields_with_context = defaultdict(list)

    # Loop through schematron validation results
    for result in xml_root:
        for vr in result.findall("validationResult"):
            try:
                issue = vr.find("issue")
                if issue is None:
                    continue
                message_elem = issue.find("message")
                context_elem = issue.find("context")
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
                xpath = context_elem.text
                # Add xpath if not already present (avoiding duplicates)
                if xpath not in data_fields_with_context[err_data_field]:
                    data_fields_with_context[err_data_field].append(xpath)

            except Exception as e:
                # TODO: we may want to log this somewhere instead of print
                print(f"Error parsing schematron output: {e}")
                continue
    return data_fields_with_context


def _enhance_xpath_with_namespace(xpath: str, namespace: str) -> str:
    """Enhance an XPath with the specified namespace.

    :param base_xpath: The base XPath to enhance.
    :param namespace: The namespace to apply to the base XPath.
    :returns: The enhanced XPath with the specified namespace.
    """
    # split the xpath into parts
    parts = xpath.strip().split("/")
    enhanced_parts = []
    for part in parts:
        if part == "ClinicalDocument":
            continue
        if (
            part
            and not part.startswith(namespace + ":")
            and part.startswith("@") is False
            and part.endswith("()") is False
        ):
            enhanced_parts.append(f"{namespace}:{part}")
        else:
            enhanced_parts.append(part)
    enhanced_xpath = "." + "/".join(enhanced_parts)
    return enhanced_xpath


def get_text_candidates(eicr_data: str, base_xpath: str, data_field: str) -> dict:
    """Find text candidates for a specified data field/element.

    :param eicr_data: The eICR data as an XML string.
    :param base_xpath: The base XPath to use to find text candidates
        within the eICR for the specified data field.
    :param data_field: The data field/element of interest for TTC processing.
    :returns: A list of text candidates found within the eICR for
        the specified data field/element for TTC processing.
    """
    text_candidates = {}
    # first get data field config settings - this acts
    # as a validation of correct data field being passed
    config_settings = get_configuration_for_data_element(data_field)

    if not eicr_data.strip() or not base_xpath.strip() or config_settings is None:
        return text_candidates

    # get list of xpaths per data field from config
    sub_xpaths = config_settings.xpaths

    # enhance the base xpath with the namespace
    enhanced_base_xpath = _enhance_xpath_with_namespace(base_xpath, "cda")

    try:
        xml_root = etree.fromstring(eicr_data.encode("utf-8"))
        nodes = xml_root.xpath(enhanced_base_xpath, namespaces=NAMESPACES)
        for node in nodes:
            for sub_xpath in sub_xpaths:
                enhanced_xpath = _enhance_xpath_with_namespace(sub_xpath, "cda")
                sub_nodes = node.xpath(enhanced_xpath, namespaces=NAMESPACES)
                for i, sub_node in enumerate(sub_nodes):
                    if len(sub_node.strip()) > 0:
                        # NOTE: I've added the iterator at the end of the key to ensure uniqueness
                        # per key in the case that there may be multiple locations where the text
                        # candidate may be the same
                        text_candidates[f"{base_xpath}{sub_xpath}[{i}]"] = sub_node.strip()
    except Exception as e:
        # TODO: we may want to log this somewhere instead of print
        print(f"Error extracting text from eicr message: {e}")
        return text_candidates
    return text_candidates
