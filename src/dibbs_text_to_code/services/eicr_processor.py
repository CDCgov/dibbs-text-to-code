from lxml import etree
from lxml.etree import Element

from dibbs_text_to_code.models import eicr
from dibbs_text_to_code.services import utils

NAMESPACES = {
    "cda": "urn:hl7-org:v3",
    "sdtc": "urn:hl7-org:sdtc",
    "voc": "http://www.lantanagroup.com/voc",
    "xsi": "http://www.w3.org/2001/XMLSchema-instance",
}


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


def get_text_candidates(eicr_data: str, base_xpath: str, data_field: eicr.EicrDataField) -> dict:
    # TODO: Update output here to be better typed to reflect the allowable xpaths
    """Find text candidates for a specified data field.

    :param eicr_data: The eICR data as an XML string.
    :param base_xpath: The base XPath to use to find text candidates
        within the eICR for the specified data field.
    :param data_field: The data field of interest for TTC processing.
    :returns: A list of text candidates found within the eICR for
        the specified data field for TTC processing.
    """
    text_candidates = {}
    # get data field config settings
    config_settings = utils.get_config_for_data_field(data_field)

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
                    # NOTE: I've added the iterator at the end of the key to ensure uniqueness
                    # per key in the case that there may be multiple locations where the text
                    # candidate may be the same
                    key = f"{base_xpath}{sub_xpath}[{i}]"

                    if isinstance(sub_node, str):
                        if sub_node.strip():
                            text_candidates[key] = sub_node.strip()
                    else:
                        text = _extract_text_from_element(sub_node, xml_root)
                        if text:
                            text_candidates[key] = text

    except Exception as e:
        # TODO: we may want to log this somewhere instead of print
        print(f"Error extracting text from eicr message: {e}")
        return text_candidates
    return text_candidates


def resolve_reference(xml_root: Element, reference_value: str | None) -> str | None:
    """Get the text of the first node with an ID attribute that matches the reference."""
    if not reference_value:
        return None

    referenced_node = xml_root.find(f'.//*[@ID="{reference_value.strip("#")}"]')

    if referenced_node is not None:
        return " ".join(_get_text_recursively(referenced_node))

    return None


def _get_text_recursively(element: Element) -> list[str]:
    text_elements = []
    if element.text:
        text_elements.append(element.text.strip())

    for child in element:
        text_elements += _get_text_recursively(child)

    if element.tail:
        text_elements.append(element.tail.strip())

    return list(filter(lambda x: x, text_elements))


def _extract_text_from_element(element: Element, xml_root: Element) -> str:
    """Extract all text content from an element, including referenced content.

    :param element: The element to extract text from.
    :param xml_root: The root XML element for resolving references.
    :returns: Concatenated text content from the element.
    """
    text_parts = []

    if element.text:
        text_parts.append(element.text.strip())

    for child in element:
        # Handle reference elements
        if child.tag == "{urn:hl7-org:v3}reference":
            ref_text = resolve_reference(xml_root, child.get("value"))
            if ref_text:
                text_parts.append(ref_text)
        else:
            # Recursively get text from child elements
            text_parts.extend(_get_text_recursively(child))

        if child.tail:
            text_parts.append(child.tail.strip())

    return " ".join(filter(None, text_parts))
