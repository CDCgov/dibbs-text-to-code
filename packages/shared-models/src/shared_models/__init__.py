from enum import StrEnum

from pydantic import BaseModel, ConfigDict

LOINC_NAME = "LOINC"
LOINC_OID = "2.16.840.1.113883.6.1"
LOINC_URL = "http://loinc.org"
LOINC_URN = f"urn:oid:{LOINC_OID}"

SNOMED_OID = "2.16.840.1.113883.6.96"
SNOMED_URL = "http://snomed.info/sct"
SNOMED_URN = f"urn:oid:{SNOMED_OID}"


class FrozenBaseModel(BaseModel):
    """A custom base model that all other models can inherit so that they are frozen and do not allow extra attributes."""

    model_config = ConfigDict(frozen=True, extra="forbid", populate_by_name=True)


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


class NonstandardCodeInstance(FrozenBaseModel):
    """Model with the information needed to update a nonstandard code."""

    schematron_error_xpath: str
    """The XPath give by the Schematron error to the observation with a nonconforming code."""
    field_type: DataField
    """The `DataField` type of the nonconforming code."""
    new_translation: Code
    """The new translation."""


class PassthroughReason(StrEnum):
    """Reasons why augmentation was bypassed and the original eICR was passed through."""

    NO_RELEVANT_SCHEMATRON_ERRORS = "no_relevant_schematron_errors"
    NO_CODE_MATCHES = "no_code_matches"
    TTC_EXCEPTION = "ttc_exception"
    AUGMENTATION_EXCEPTION = "augmentation_exception"
    AUGMENTATION_VALIDATION_FAILURE = "augmentation_validation_failure"


class TTCAugmenterInput(FrozenBaseModel):
    """Input for the augmentation service."""

    persistence_id: str
    original_eicr_id: CdaInstanceIdentifier | None = None
    nonstandard_codes: list[NonstandardCodeInstance] = []
    passthrough_reason: PassthroughReason | None = None
