from lxml import etree
from lxml.etree import Element


def clean_xml_tree(doc_data: str) -> Element:
    """Remove all namespaces from an XML tree."""
    tree = etree.fromstring(doc_data.encode("utf-8"))
    for elem in tree.iter():
        # Remove namespace from tag
        elem.tag = etree.QName(elem).localname
    # Remove namespace declarations
    etree.cleanup_namespaces(tree)
    return tree
