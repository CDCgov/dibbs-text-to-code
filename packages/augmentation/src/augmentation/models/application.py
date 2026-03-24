from enum import StrEnum

from pydantic import BaseModel
from shared_models import NonstandardCodeInstance


class ApplicationCode(StrEnum):
    """The list of applications that will leveraging Augmentation functionality."""

    # element 0 - Application Code
    # element 1 - Application Code Display Name (for human readability)
    TEXT_TO_CODE = ("text-to-code", "Text-to-Code")

    def __new__(cls, code: str, display: str):  # noqa: ANN204, D102
        # use the base type's __new__ to create the enum instance
        obj = str.__new__(cls, code)
        obj._value_ = code
        obj.display = display
        obj.code = code
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
