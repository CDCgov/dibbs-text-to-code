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
    def test_clean_xml_tree(self):
        result = eicr_utils.clean_xml_tree(EICR_OUTPUT)
        assert len(result) < len(EICR_OUTPUT)

    def test_clean_xml_tree_with_comments(self):
        result = eicr_utils.clean_xml_tree(COVID_ECR)
        assert len(result) < len(COVID_ECR)
