from pathlib import Path

from validation.main import validate_eicr


def test_validation():
    with Path.open(
        "/Users/jnygaard/Dev/Skylight/Dibbs/dibbs-text-to-code/e2e/assets/test_eicr.xml"
    ) as f:
        eicr = f.read()
    validate_eicr(eicr, True)
