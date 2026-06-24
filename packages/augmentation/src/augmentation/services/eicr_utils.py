from lxml import etree
from lxml.etree import Element

CDA_NS = "urn:hl7-org:v3"
CDA_NSMAP = {"cda": CDA_NS}


def _parse_eicr_xml(doc_data: str) -> Element:
    """Parse an eICR XML document, preserving all namespace declarations."""
    return etree.fromstring(doc_data.encode("utf-8"))


def cda_xpath(xpath: str) -> str:
    """Prefix unprefixed element steps in an eICR XPath with the 'cda' prefix.

    The augmenter accepts XPaths written against the eICR without namespace
    prefixes (e.g. '/ClinicalDocument/id'). Once the tree carries its real
    namespaces, those XPaths must be rewritten to '/cda:ClinicalDocument/cda:id'
    and evaluated with namespaces={'cda': 'urn:hl7-org:v3'}.

    Leading/trailing whitespace is stripped because schematron `<context>`
    elements emitted upstream often carry surrounding indentation.
    """
    parts = xpath.strip().split("/")
    rewritten = []
    for part in parts:
        if not part or part.startswith("@") or part == "*" or ":" in part or "(" in part:
            rewritten.append(part)
        else:
            rewritten.append(f"cda:{part}")
    return "/".join(rewritten)


def cda_element(tag: str, parent: Element | None = None) -> Element:
    """Create an element in the CDA default namespace (urn:hl7-org:v3)."""
    full_tag = f"{{{CDA_NS}}}{tag}"
    if parent is not None:
        return etree.SubElement(parent, full_tag)
    return etree.Element(full_tag)


def parse_document(xml: str) -> Element:
    """Parse and validate an eICR XML document, raising if empty."""
    if not xml or not xml.strip():
        raise ValueError("Document payload must be a non-empty string!")
    return _parse_eicr_xml(xml)
