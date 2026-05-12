from enum import StrEnum

from pydantic import BaseModel
from pydantic import ConfigDict


class CdaInstanceIdentifier(BaseModel):
    """CDA Instance Identifier (II) data type.

    https://build.fhir.org/ig/HL7/CDA-core-2.0/StructureDefinition-II.html
    """

    null_flavor: str | None = None
    assigning_authority_name: str | None = None
    displayable: bool | None = None
    root: str | None = None
    extension: str | None = None


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


class NonstandardCodeReplacement(BaseModel):
    """Model with the information needed to update a nonstandard code."""

    schematron_error_xpath: str
    """The XPath give by the Schematron error to the observation with a nonconforming code."""
    field_type: DataField
    """The `DataField` type of the nonconforming code."""
    new_translation: Code
    """The new translation."""


class TTCOutput(BaseModel):
    """The data that will be sent to the augmentation Lambda."""

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    persistence_id: str
    nonstandard_codes: list[NonstandardCodeReplacement]
