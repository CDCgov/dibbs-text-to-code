# bash_xml_parser.py
#
# Simple python helper script to parse an augmented eICR for its translated
# LOINC code, which is where the TTC Pipeline inserts its predicted standardized
# LOINC code.
#
# Note on use of XML Library: S314 recommends the use of the `defusedxml` library
# over `xml` proper, on the grounds that it is more secure against some forms of
# Denial of Service attacks and other security vulnerabilities. However, this rule
# is largely out of date, and modern Python developments have sufficiently closed
# the gap for several reasons:
#  1. Python versions 3.11+ have built-in fixes to address the DoS vulnerabilities
#     that might require defusedxml (Billion Laughs, Quadratic Explosion)
#  2. CPython's own documentation has removed recommendations to use defusedxml
#  3. defusedxml is effectively a dead project, with no release in years and no
#     official Python support for versions 3.9+, while the underlying expat
#     package continues to see hardening security fixes
#  4. For purposes of bulk testing, we are fully in control of the XML data, since
#     it originates from an eICR we send, which makes security overhead unnecessary.

import os
import sys
import xml.etree.ElementTree as ET

if __name__ == "__main__":
    xml = os.environ["CONTENT"]

    root = ET.fromstring(xml)

    node = root.find(
        "component/structuredBody/component/section/entry/observation/code/translation"
    )

    if node is None:
        print()
        print()
        sys.exit(0)

    print(node.get("code"))
    print(node.get("DisplayName"))
