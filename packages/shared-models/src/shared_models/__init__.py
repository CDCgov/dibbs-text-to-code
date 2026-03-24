from enum import StrEnum

from pydantic import BaseModel
from pydantic import ConfigDict
from pydantic import Field


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


class S3Location(BaseModel):
    """Represents the location of a file in S3, indicating which file contained the relevant data."""

    bucket: str = Field(description="The S3 bucket where the file is located.")
    key: str = Field(description="The S3 key (path) where the file is located.")


class OpenSearchHitSource(BaseModel):
    """Represents a single search result _source returned from OpenSearch."""

    id: int = Field(description="The unique ID from the embedding data of the search result hit.")
    loinc_code: str = Field(description="The LOINC code of the search result hit.")
    loinc_name_type: str = Field(description="The LOINC name type of the search result hit.")
    description: str = Field(description="The description of the search result hit.")
    loinc_type: str = Field(description="The LOINC type of the search result hit.")
    s3: S3Location = Field(description="The S3 location of the search result hit.")
