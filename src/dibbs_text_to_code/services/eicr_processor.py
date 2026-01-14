from lxml import etree
from lxml.etree import Element

from dibbs_text_to_code.configs.general import get_configuration_for_data_element

NAMESPACES = {
    "cda": "urn:hl7-org:v3",
    "sdtc": "urn:hl7-org:sdtc",
    "voc": "http://www.lantanagroup.com/voc",
    "xsi": "http://www.w3.org/2001/XMLSchema-instance",
}


class EicrProcessor:
    """Processors an EICR."""

    def __init__(self, eicr_data: str):
        """Initialize an EicrProcessor.

        :param self
        :param eicr_data: string of EICR
        """
        self._xml_root = etree.fromstring(eicr_data.encode("utf-8"))

    def _get_by_xpath(self, *xpath: str) -> Element:
        return self._xml_root.xpath("/".join(xpath))

    def get_text_candidates(self, base_xpath: str, data_field: str) -> dict[str, str]:
        """Find text candidates for a specified data field/element.

        :param eicr_data: The eICR data as an XML string.
        :param base_xpath: The base XPath to use to find text candidates
            within the eICR for the specified data field.
        :param data_field: The data field/element of interest for TTC processing.
        :returns: A list of text candidates found within the eICR for
            the specified data field/element for TTC processing.
        """
        text_candidates: dict[str, str] = {}
        # first get data field config settings - this acts
        # as a validation of correct data field being passed
        config_settings = get_configuration_for_data_element(data_field)

        if not base_xpath.strip() or config_settings is None:
            return text_candidates

        # get list of xpaths per data field from config
        sub_xpaths = config_settings.xpaths

        try:
            nodes = self._get_by_xpath(base_xpath)
            for _ in nodes:
                for sub_xpath in sub_xpaths:
                    sub_nodes = self._get_by_xpath(base_xpath, sub_xpath)
                    for i, sub_node in enumerate(sub_nodes):
                        key = f"{base_xpath}{sub_xpath}[{i}]"

                        if isinstance(sub_node, str):
                            if sub_node.strip():
                                text_candidates[key] = sub_node.strip()
                        else:
                            text = self._extract_text_from_element(sub_node)
                            if text:
                                text_candidates[key] = text

        except Exception as e:
            # TODO: we may want to log this somewhere instead of print
            print(f"Error extracting text from eicr message: {e}")
            return text_candidates
        return text_candidates

    def resolve_reference(self, reference_value: str | None) -> str | None:
        """Get the text of the first node with an ID attribute that matches the reference."""
        if not reference_value:
            return None

        referenced_node = self._xml_root.find(f'.//*[@ID="{reference_value.strip("#")}"]')

        if referenced_node is not None:
            return " ".join(_get_text_recursively(referenced_node))

        return None

    def _extract_text_from_element(self, element: Element) -> str:
        """Extract all text content from an element, including referenced content.

        :param xml_root: The root XML element for resolving references.
        :returns: Concatenated text content from the element.
        """
        text_parts = []

        if element.text:
            text_parts.append(element.text.strip())

        for child in element:
            # Handle reference elements
            if child.tag == "{urn:hl7-org:v3}reference":
                ref_text = self.resolve_reference(child.get("value"))
                if ref_text:
                    text_parts.append(ref_text)
            else:
                # Recursively get text from child elements
                text_parts.extend(_get_text_recursively(child))

            if child.tail:
                text_parts.append(child.tail.strip())

        return " ".join(filter(None, text_parts))


def _get_text_recursively(element: Element) -> list[str]:
    text_elements = []
    if element.text:
        text_elements.append(element.text.strip())

    for child in element:
        text_elements += _get_text_recursively(child)

    if element.tail:
        text_elements.append(element.tail.strip())

    return list(filter(lambda x: x, text_elements))
