from enum import StrEnum

from pydantic import BaseModel


class LabXPaths(StrEnum):
    """The list of Sub XPath expressions to extract text in various locations from lab elements."""

    CODE_DISPLAY_NAME = "/code/@displayName"
    CODE_ORIGINAL_TEXT = "/code/originalText"
    CODE_TEXT = "/text"
    CODE_TRANSLATION_DISPLAY_NAME = "/code/translation/@displayName"
    CODE_TRANSLATION_ORIGINAL_TEXT = "/code/translation/originalText"


class Candidate(BaseModel):
    """Model representing a piece of text to be considered for encoding."""

    value: str
    xpath: LabXPaths
    system: str | None = None


class EicrMetadata(BaseModel):
    """Model representing metadata extracted from an eICR."""

    eicr_id: str | None = None
    eicr_vendor: str | None = None
