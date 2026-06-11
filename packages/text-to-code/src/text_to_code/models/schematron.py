from enum import Enum

from shared_models import CdaInstanceIdentifier, DataField, FrozenBaseModel
from text_to_code.models.eicr import Candidate


class LabTestNameOrderedSchematronErrors(Enum):
    """The list of Schematron error message ids that are relevant to the lab test name ordered data field."""

    MISSING_CODE_ATTRIBUTE = "ttc-labOrder-code-missing"
    BLANK_CODE_ATTRIBUTE = "ttc-labOrder-code-empty"
    NULL_CODE_ATTRIBUTE = "ttc-labOrder-code-nullFlavor"
    INVALID_CODE_SYSTEM = "ttc-labOrder-wrongCode"


class LabTestNameResultedSchematronErrors(Enum):
    """The list of Schematron error message ids that are relevant to the lab test name resulted data field."""

    MISSING_CODE_ATTRIBUTE = "ttc-labTestNameResulted-noCode"
    BLANK_CODE_ATTRIBUTE = "ttc-labTestNameResulted-code-empty"
    NULL_CODE_ATTRIBUTE = "ttc-labTestNameResulted-code-nullFlavor"
    INVALID_CODE_SYSTEM = "ttc-labTestNameResulted-wrongCode"


SchematronErrors = LabTestNameOrderedSchematronErrors | LabTestNameResultedSchematronErrors

# Map each Schematron error enum to its corresponding DataField
_SCHEMATRON_ENUM_TO_FIELD: dict[type[Enum], DataField] = {
    LabTestNameOrderedSchematronErrors: DataField.LAB_TEST_NAME_ORDERED,
    LabTestNameResultedSchematronErrors: DataField.LAB_TEST_NAME_RESULTED,
}


class SchematronConfig(FrozenBaseModel):
    """Config for Schematron configuration settings."""

    data_field: DataField
    """The data field this configuration applies to."""

    schematron_errors: list[SchematronErrors]
    """The list of Schematron error messages relevant to the data field."""


class SchematronErrorDetail(FrozenBaseModel):
    """Structured details for a Schematron validation error."""

    eicr_id: CdaInstanceIdentifier | None = None
    """The eICR identifier associated with the error, if present."""

    field: DataField
    """The data field associated with the error."""

    error: str
    """The normalized Schematron error value."""

    error_message: str
    """The Schematron error message."""

    error_context: str
    """The XPath context associated with the error."""

    error_test: str | None = None
    """The Schematron test expression associated with the error."""

    error_id: str | None = None
    """The Schematron identifier associated with the error, if present."""

    candidate: Candidate | None = None
    """The selected candidate associated with the error, if present."""
