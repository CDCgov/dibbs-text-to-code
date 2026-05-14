from enum import StrEnum

from pydantic import BaseModel
from pydantic import ConfigDict


class FrozenBaseModel(BaseModel):
    """A custom base model that all other models can inherit so that they are frozen and do not allow extra attributes."""

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )


class CdaInstanceIdentifier(FrozenBaseModel):
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


class Code(FrozenBaseModel):
    """Model for CDA "ConceptDescriptor". This is the type of the new translation."""

    code: str | None = None
    code_system: str | None = None
    code_system_name: str | None = None
    display_name: str | None = None
    value_set: str | None = None
    value_set_version: str | None = None
    original_text: str | None = None


class NonstandardCodeReplacement(FrozenBaseModel):
    """Model with the information needed to update a nonstandard code."""

    schematron_error_xpath: str
    """The XPath give by the Schematron error to the observation with a nonconforming code."""
    field_type: DataField
    """The `DataField` type of the nonconforming code."""
    new_translation: Code
    """The new translation."""


class TTCOutput(FrozenBaseModel):
    """Input for the augmentation service."""

    persistence_id: str
    nonstandard_codes: list[NonstandardCodeReplacement]
