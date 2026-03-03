"""TTC -> Augmentation e2e.

1) load test data
2) Pass to TTC
3) Pass output of Text to Code to Augmentation
"""

from pathlib import Path

from augmentation import augment
from text_to_code import text_to_code


class TestTTCAugmentationE2E:
    def test_e2e(self):
        assets_dir = Path(__file__).parent / "assets"
        with (assets_dir / "eICR Sample Patient Alliance 03132020.xml").open() as file:
            eicr = file.read()
        with (
            assets_dir / "eICR Sample Patient Alliance 03132020_validation_report.svrl"
        ).open() as file:
            schematron_output = file.read()

            augmentation_input = text_to_code(eicr, schematron_output)

            augment(augmentation_input)

        assert True
