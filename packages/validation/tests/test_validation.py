from pathlib import Path

from validation import validate_eicr


def test_validation():
    with Path.open("packages/validation/tests/assets/test_eicr.xml") as f:
        eicr = f.read()
    results = validate_eicr(eicr, True)

    assert results == [
        {
            "error_id": "ttc-labTestNameOrdered-noCode",
            "location": "/Q{urn:hl7-org:v3}ClinicalDocument[1]/Q{urn:hl7-org:v3}component[1]/Q{urn:hl7-org:v3}structuredBody[1]/Q{urn:hl7-org:v3}component[1]/Q{urn:hl7-org:v3}section[1]/Q{urn:hl7-org:v3}entry[1]/Q{urn:hl7-org:v3}observation[1]",
        }
    ]


def test_validation_no_errors():
    with Path.open("e2e/snapshots/test_e2e/test_upload_and_process/augmented_eicr.xml") as f:
        eicr = f.read()
    results = validate_eicr(eicr, True)

    assert results == []
