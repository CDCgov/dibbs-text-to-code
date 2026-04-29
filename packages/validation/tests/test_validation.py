from pathlib import Path

from validation.main import validate_eicr


def test_validation():
    with Path.open(
        "/Users/jnygaard/Dev/Skylight/Dibbs/dibbs-text-to-code/e2e/assets/test_eicr.xml"
    ) as f:
        eicr = f.read()
    results = validate_eicr(eicr, True)

    assert results == [
        {
            "error_id": "ttc-labTestNameOrdered-noCode",
            "location": "/Q{urn:hl7-org:v3}ClinicalDocument[1]/Q{urn:hl7-org:v3}component[1]/Q{urn:hl7-org:v3}structuredBody[1]/Q{urn:hl7-org:v3}component[1]/Q{urn:hl7-org:v3}section[1]/Q{urn:hl7-org:v3}entry[1]/Q{urn:hl7-org:v3}observation[1]",
        }
    ]
