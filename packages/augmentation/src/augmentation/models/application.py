from enum import StrEnum

from pydantic import BaseModel
from pydantic import ConfigDict

from shared_models import NonstandardCodeInstance


class ApplicationCode(StrEnum):
    """The list of applications that will leveraging Augmentation functionality."""

    display: str

    # element 0 - Application Code
    # element 1 - Application Code Display Name (for human readability)
    TEXT_TO_CODE = ("text-to-code", "Text-to-Code")

    def __new__(cls, value: str, display: str) -> "ApplicationCode":
        """Create a new instance of the ApplicationCode enum with code and display attributes."""
        # use the base type's __new__ to create the enum instance
        obj = object.__new__(cls)
        obj._value_ = value
        obj.display = display
        return obj


class NonstandardCodeInstanceMetadata(NonstandardCodeInstance):
    """Model for the metadata for each instance of a nonstandard code.

    This is the same as the `NonstandardCodeInstance` model, but includes the path to the new translation.
    """

    new_translation_xpath: str
    """XPath to the translation added to the augmented eICR with the standard code."""


class Metadata(BaseModel):
    """Model to hold augmentation metadata."""

    original_eicr_id: str
    augmented_eicr_id: str
    nonstandard_codes: list[NonstandardCodeInstanceMetadata]
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
