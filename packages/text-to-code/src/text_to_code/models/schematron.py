from enum import Enum

from pydantic import BaseModel

from shared_models import DataField


class LabTestNameOrderedSchematronErrors(Enum):
    """The list of Schematron error messages relevant to the lab test name ordered data field."""

    MISSING_CODE_ATTRIBUTE = "Text to Code: Lab Test Name Ordered does not have a @code attribute"
    INVALID_CODE_SYSTEM = "Text to Code: Lab Test Name Ordered code and translation data elements @codeSystem attribute are not LOINC 2.16.840.1.113883.6.1"


class LabTestNameResultedSchematronErrors(Enum):
    """The list of Schematron error messages relevant to the lab test name resulted data field."""

    MISSING_CODE_ATTRIBUTE = "Text to Code: Lab Test Name Resulted does not have a @code attribute"
    INVALID_CODE_SYSTEM = "Text to Code: Lab Test Name Resulted code and translation data elements @codeSystem attribute are not LOINC 2.16.840.1.113883.6.1"


SchematronErrors = LabTestNameOrderedSchematronErrors | LabTestNameResultedSchematronErrors

# Map each Schematron error enum to its corresponding DataField
_SCHEMATRON_ENUM_TO_FIELD: dict[type[Enum], DataField] = {
    LabTestNameOrderedSchematronErrors: DataField.LAB_TEST_NAME_ORDERED,
    LabTestNameResultedSchematronErrors: DataField.LAB_TEST_NAME_RESULTED,
}


class SchematronConfig(BaseModel):
    """Config for Schematron configuration settings."""

    data_field: DataField
    """The data field this configuration applies to."""

    schematron_errors: list[SchematronErrors]
    """The list of Schematron error messages relevant to the data field."""
