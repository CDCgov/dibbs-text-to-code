from pathlib import Path

from augmentation.services import eicr_utils

EXAMPLE_EICRS_DIRECTORY = Path(__file__).parent.parent / "assets"
eicr_path = EXAMPLE_EICRS_DIRECTORY / "basic_test_eicr.xml"
with eicr_path.open() as f:
    EICR_OUTPUT = f.read()

covid_ecr_path = EXAMPLE_EICRS_DIRECTORY / "test_eicr_covid.xml"
with covid_ecr_path.open() as f:
    COVID_ECR = f.read()


class TestEicrUtils:
    def test_parse_eicr_xml_preserves_default_namespace(self):
        result = eicr_utils.parse_eicr_xml(EICR_OUTPUT)
        assert result.tag == f"{{{eicr_utils.CDA_NS}}}ClinicalDocument"
        assert result.nsmap.get(None) == eicr_utils.CDA_NS

    def test_parse_eicr_xml_preserves_sdtc_namespace(self):
        result = eicr_utils.parse_eicr_xml(COVID_ECR)
        assert result.nsmap.get("sdtc") == "urn:hl7-org:sdtc"

    def test_cda_xpath_prefixes_unprefixed_elements(self):
        assert eicr_utils.cda_xpath("/ClinicalDocument/id") == "/cda:ClinicalDocument/cda:id"

    def test_cda_xpath_leaves_attributes_unchanged(self):
        assert (
            eicr_utils.cda_xpath("/ClinicalDocument/id/@root")
            == "/cda:ClinicalDocument/cda:id/@root"
        )

    def test_cda_xpath_strips_surrounding_whitespace(self):
        # Schematron <context> elements often emit XPath surrounded by indentation
        # whitespace; lxml's xpath() is lenient about it but our rewriter must
        # tolerate it too.
        assert (
            eicr_utils.cda_xpath("\n    /ClinicalDocument/component[1]/observation[1]  ")
            == "/cda:ClinicalDocument/cda:component[1]/cda:observation[1]"
        )
