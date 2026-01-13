from lxml import etree

from dibbs_text_to_code.configs.general import get_configuration_for_data_element

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


# def get_reference_value(reference_value: str) -> str | None:
#     """Get the text of the first node with an ID attribute that matches the reference."""
#     referenced_node = self.eicr.find(f'.//*[@ID="{reference_value.strip("#")}"]')

#     if referenced_node is not None:
#         return referenced_node.text

#     return None
