from enum import StrEnum
from typing import TypedDict

from pydantic import BaseModel
from pydantic import ConfigDict
from pydantic import Field

AUGMENTATION_METADATA_PREFIX = "AugmentationMetadata/"
AUGMENTED_EICR_PREFIX = "AugmentationEICRV2/"
EICR_INPUT_PREFIX = "eCRMessageV2/"
S3_BUCKET = "dibbs-text-to-code"
SCHEMATRON_ERROR_PREFIX = "schematronErrors/"
TTC_INPUT_PREFIX = "TextToCodeValidateSubmissionV2/"
TTC_METADATA_PREFIX = "TTCMetadata/"
TTC_OUTPUT_PREFIX = "TTCOutput/"


class CdaInstanceIdentifier(BaseModel):
    """CDA Instance Identifier (II) data type.

    https://build.fhir.org/ig/HL7/CDA-core-2.0/StructureDefinition-II.html
    """

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

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    schematron_error_xpath: str
    """The XPath give by the Schematron error to the observation with a nonconforming code."""
    field_type: DataField
    """The `DataField` type of the nonconforming code."""
    new_translation: Code
    """The new translation."""


class EICRMetadata(BaseModel):
    """Model representing metadata about the eICR."""

    eicr_id: CdaInstanceIdentifier
    eicr_vendor: str | None = None


class TTCOutput(BaseModel):
    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )
    message: str | None
    persistance_id: str
    nonstandard_codes: list[NonstandardCodeReplacement]


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


class OpenSearchHit(BaseModel):
    """Represents a single search result hit returned from OpenSearch."""

    model_config = ConfigDict(populate_by_name=True)

    index: str = Field(
        description="The index that the search result hit came from.", alias="_index"
    )
    id: str = Field(description="The unique OpenSearch ID of the search result hit.", alias="_id")
    score: float = Field(
        description="The cosine similarity score of the search result hit.", alias="_score"
    )
    source: OpenSearchHitSource = Field(
        description="The source of the search result hit.", alias="_source"
    )


class LabXPaths(StrEnum):
    """The list of Sub XPath expressions to extract text in various locations from lab elements."""

    CODE_DISPLAY_NAME = "code/@displayName"
    CODE_ORIGINAL_TEXT = "code/originalText"
    OBSERVATION_TEXT = "text"
    CODE_TRANSLATION_DISPLAY_NAME = "code/translation/@displayName"
    CODE_TRANSLATION_ORIGINAL_TEXT = "code/translation/originalText"


class Candidate(BaseModel):
    """Model representing a piece of text to be considered for encoding."""

    value: str
    xpath: LabXPaths
    system: str | None = None


class OpenSearchHits(BaseModel):
    """Represents all of the search result hits returned from OpenSearch."""

    model_config = ConfigDict(populate_by_name=True)

    total_hits: dict[str, int] = Field(
        alias="total", description="The total number of hits returned from OpenSearch."
    )
    hits: list[OpenSearchHit] = Field(
        description="The list of search result hits returned from OpenSearch."
    )


class OpenSearchShards(BaseModel):
    """Represents the shard information returned from OpenSearch."""

    total: int = Field(description="The total number of shards involved in the search.")
    successful: int = Field(description="The number of shards that successfully returned results.")
    skipped: int = Field(description="The number of shards that were skipped during the search.")
    failed: int = Field(description="The number of shards that failed to return results.")


class SortedRank(TypedDict):
    code_string: str
    score: float


class OpenSearchResult(BaseModel):
    """Represents the overall search result returned from OpenSearch, including hits and shard information."""

    model_config = ConfigDict(populate_by_name=True)

    took: int = Field(description="The time taken to execute the search in milliseconds.")
    timed_out: bool = Field(description="Indicates whether the search timed out.")
    shards: OpenSearchShards = Field(
        description="The shard information for the search.", alias="_shards"
    )
    hits: OpenSearchHits = Field(description="The search result hits returned from OpenSearch.")


class SchematronErrorDetail(BaseModel):
    """Structured details for a Schematron validation error."""

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
    opensearch_retrieved_scores: OpenSearchResult | None = None
    reranker_processed_results: list[SortedRank] | None = None

    new_translation: Code | None = None

    def to_nonstandard_code_replacement(self) -> NonstandardCodeReplacement:
        return NonstandardCodeReplacement(
            schematron_error_xpath=self.error_context,
            field_type=self.field,
            new_translation=self.new_translation,
        )
