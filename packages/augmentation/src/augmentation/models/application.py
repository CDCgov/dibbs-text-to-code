from enum import Enum

from pydantic import BaseModel
from pydantic import ConfigDict

from shared_models import NonstandardCodeReplacement


class ApplicationCode(Enum):
    """The list of applications that will leveraging Augmentation functionality."""

    code: str
    display: str
    TEXT_TO_CODE = ("text-to-code", "Text-to-Code")

    def __new__(cls, value: str, display: str) -> "ApplicationCode":
        """Initialize ApplicationCode enum."""
        obj = object.__new__(cls)
        obj._value_ = value
        obj.display = display
        obj.code = value
        return obj


class NonstandardCodeReplacementMetadata(NonstandardCodeReplacement):
    """Model for the metadata for each instance of a nonstandard code.

    This is the same as the `NonstandardCodeReplacement` model, but includes the path to the new translation.
    """

    new_translation_xpath: str
    """XPath to the translation added to the augmented eICR with the standard code."""


class Metadata(BaseModel):
    """Model to hold augmentation metadata."""

    original_eicr_id: str
    augmented_eicr_id: str
    nonstandard_codes: list[NonstandardCodeReplacementMetadata]
    """List of the nonstandard codes TTC attempted to resolve."""
    error: str | None = None


class TTCAugmenterOutput(BaseModel):
    """Output of the augmentation service."""

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    eicr_id: str
    augmented_eicr: str
    metadata: Metadata
