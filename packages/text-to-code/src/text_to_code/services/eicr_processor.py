from lxml import etree
from lxml.etree import Element
from shared_models import II
from shared_models import DataField

from text_to_code.models import Candidate
from text_to_code.models.eicr import Metadata
from text_to_code.services.utils import get_config_for_data_field


class EicrProcessor:
    """Processes an eICR."""

    def __init__(self, eicr_data: str):
        """Initialize an eICR Processor.

        :param eicr_data: string of eICR
        """
        self._xml_root = _create_xml_tree(eicr_data)

    def _get_by_xpath(self, xpath: str) -> Element:
        return self._xml_root.xpath(xpath)

    def get_text_candidates(self, base_xpath: str, data_field: DataField) -> list[Candidate]:
        """Find text candidates for a specified data field/element.

        :param base_xpath: The base XPath to use to find text candidates
            within the eICR for the specified data field.
        :param data_field: The data field of interest for TTC processing.
        :returns: A list of text candidates found within the eICR for
            the specified data field for TTC processing.
        """
        candidates: list[Candidate] = []
        # first get data field config settings - this acts
        # as a validation of correct data field being passed
        config_settings = get_config_for_data_field(data_field)

        if not base_xpath.strip() or config_settings is None:
            return candidates

        # get list of xpaths per data field from config
        sub_xpaths = config_settings.xpaths

        try:
            nodes = self._get_by_xpath(base_xpath)
            for _ in nodes:
                for sub_xpath in sub_xpaths:
                    full_xpath = f"{base_xpath}/{sub_xpath}"
                    sub_nodes = self._get_by_xpath(full_xpath)
                    for sub_node in sub_nodes:
                        key = sub_xpath

                        if isinstance(sub_node, str):
                            text: str = sub_node.strip()
                            if text:
                                candidates.append(Candidate(value=text, xpath=key))
                        else:
                            text = self._extract_text_from_element(sub_node)
                            if text:
                                candidates.append(Candidate(value=text, xpath=key))

        except Exception as e:
            # TODO: we may want to log this somewhere instead of print
            print(f"Error extracting text from eicr message: {e}")
            return candidates
        return candidates

    def resolve_reference(self, reference_value: str | None) -> str | None:
        """Get the text of the first node with an ID attribute that matches the reference."""
        reference_value = reference_value.strip() if reference_value else ""
        if not reference_value:
            return None

        referenced_node = self._xml_root.find(f'.//*[@ID="{reference_value.strip("#")}"]')

        if referenced_node is not None:
            return " ".join(_get_text_recursively(referenced_node))

        return None

    def _extract_text_from_element(self, element: Element) -> str:
        """Extract all text content from an element, including referenced content.

        :param element: The XML element.
        :returns: Concatenated text content from the element.
        """
        text_parts = []

        if element.text:
            text_parts.append(element.text.strip())

        for child in element:
            # Handle reference elements
            if child.tag == "reference":
                ref_text = self.resolve_reference(child.get("value"))
                if ref_text:
                    text_parts.append(ref_text)
            else:
                # Recursively get text from child elements
                text_parts.extend(_get_text_recursively(child))

            if child.tail:
                text_parts.append(child.tail.strip())

        return " ".join(filter(None, text_parts))

    @property
    def eicr_metadata(self) -> Metadata:
        """Get the eICR ID from the XML."""
        id_element = self._xml_root.find(".//id")
        if id_element is None or id_element.get("nullFlavor") is not None:
            raise ValueError("No ID element found in eICR XML.")
        instance_identifer = II(
            root=id_element.get("root"),
            extension=id_element.get("extension"),
            assigning_authority_name=id_element.get("assigningAuthorityName"),
            displayable=_to_bool(id_element.get("displayable")),
            null_flavor=id_element.get("nullFlavor"),
        )
        vendor = self._xml_root.find(
            ".//author/assignedAuthor/AuthoringDevice/manufacturerModelName"
        )
        return Metadata(
            eicr_id=instance_identifer,
            eicr_vendor=vendor.text if vendor is not None else None
        )


def _to_bool(value: str | None) -> bool | None:
    if value is None:
        return None
    if value.lower() == "true":
        return True
    if value.lower() == "false":
        return False
    return None


def _create_xml_tree(xml: str) -> Element:
    """Remove all namespaces from an XML tree."""
    tree = etree.fromstring(xml.encode("utf-8"))
    for elem in tree.iter():
        # Remove namespace from tag
        elem.tag = etree.QName(elem).localname
    # Remove namespace declarations
    etree.cleanup_namespaces(tree)
    return tree


def _get_text_recursively(element: Element) -> list[str]:
    text_elements: list[str] = []
    if element.text:
        text_elements.append(element.text.strip())

    for child in element:
        text_elements += _get_text_recursively(child)

    if element.tail:
        text_elements.append(element.tail.strip())

    return list(filter(lambda x: x, text_elements))
