from enum import StrEnum

from pydantic import BaseModel
from pydantic import ConfigDict


class DataField(StrEnum):
    """Enum for eICR data fields relevant to the TTC module."""

    LAB_TEST_NAME_RESULTED = "Lab Test Name Resulted"
    LAB_TEST_NAME_ORDERED = "Lab Test Name Ordered"


class Code(BaseModel):
    """Model for CDA "ConceptDescriptor". This is the type of the new translation."""

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    code: str | None = None
    code_system: str | None = None
    code_system_name: str | None = None
    display_name: str | None = None
    value_set: str | None = None
    value_set_version: str | None = None
    original_text: str | None = None


class NonstandardCodeInstance(BaseModel):
    """Model with the information needed to update a nonstandard code."""

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    schematron_error: str
    """The text of the Schematron error. This is only needed so that the augmentation metadata can save it."""
    schematron_error_xpath: str
    """The XPath give by the Schematron error to the observation with a nonconforming code."""
    field_type: DataField
    """The `DataField` type of the nonconforming code."""
    new_translation: Code
    """The new translation."""


class TTCAugmenterInput(BaseModel):
    """Input for the augmentation service."""

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )
    eicr_id: str
    nonstandard_codes: list[NonstandardCodeInstance]
