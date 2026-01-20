import enum

import pydantic

from dibbs_text_to_code.schemas import eicr


class LabTestNameOrderedSchematronErrors(enum.Enum):
    """The list of Schematron error messages relevant to the lab test name ordered data field."""

    MISSING_CODE_ATTRIBUTE = "Text to Code: Lab Test Name Ordered does not have a @code attribute"
    INVALID_CODE_SYSTEM = "Text to Code: Lab Test Name Ordered code and translation data elements @codeSystem attribute are not LOINC 2.16.840.1.113883.6.1"


class LabTestNameResultedSchematronErrors(enum.Enum):
    """The list of Schematron error messages relevant to the lab test name resulted data field."""

    MISSING_CODE_ATTRIBUTE = "Text to Code: Lab Test Name Resulted does not have a @code attribute"
    INVALID_CODE_SYSTEM = "Text to Code: Lab Test Name Resulted code and translation data elements @codeSystem attribute are not LOINC 2.16.840.1.113883.6.1"


SchematronErrors = LabTestNameOrderedSchematronErrors | LabTestNameResultedSchematronErrors

# Map each Schematron error enum to its corresponding EicrDataField
_SCHEMATRON_ENUM_TO_FIELD: dict[type[enum.Enum], eicr.EicrDataField] = {
    LabTestNameOrderedSchematronErrors: eicr.EicrDataField.LAB_TEST_NAME_ORDERED,
    LabTestNameResultedSchematronErrors: eicr.EicrDataField.LAB_TEST_NAME_RESULTED,
}


class SchematronConfig(pydantic.BaseModel):
    """Config for Schematron configuration settings."""

    data_field: eicr.EicrDataField
    """The data field this configuration applies to."""

    schematron_errors: list[SchematronErrors]
    """The list of Schematron error messages relevant to the data field."""


class LabXPaths(enum.StrEnum):
    """The list of Sub XPath expressions to extract text in various locations from lab elements."""

    CODE_DISPLAY_NAME = "/code/@displayName"
    CODE_ORIGINAL_TEXT = "/code/originalText"
    CODE_TEXT = "/code/text"
    CODE_TRANSLATION_DISPLAY_NAME = "/code/translation/@displayName"
    CODE_TRANSLATION_ORIGINAL_TEXT = "/code/translation/originalText"
    CODE_TRANSLATION_TEXT = "/code/translation/text"
