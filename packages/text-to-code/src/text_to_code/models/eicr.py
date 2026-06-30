from dataclasses import dataclass
from enum import StrEnum

from shared_models import CdaInstanceIdentifier, DataField, FrozenBaseModel


class LabXPaths(StrEnum):
    """The list of Sub XPath expressions to extract text in various locations from lab elements."""

    CODE_DISPLAY_NAME = "code/@displayName"
    CODE_ORIGINAL_TEXT = "code/originalText"
    OBSERVATION_TEXT = "text"
    CODE_TRANSLATION_DISPLAY_NAME = "code/translation/@displayName"
    CODE_TRANSLATION_ORIGINAL_TEXT = "code/translation/originalText"


class Candidate(FrozenBaseModel):
    """Model representing a piece of text to be considered for encoding."""

    value: str
    xpath: LabXPaths
    system: str | None = None


class Metadata(FrozenBaseModel):
    """Model representing metadata about the eICR."""

    eicr_id: CdaInstanceIdentifier | None
    eicr_vendor: str | None = None


@dataclass(frozen=True)
class TextCandidateExtractionLogContext:
    """Context for logging text candidate extraction errors and summaries."""

    base_xpath: str
    data_field: DataField
    sub_xpaths: list[LabXPaths]
