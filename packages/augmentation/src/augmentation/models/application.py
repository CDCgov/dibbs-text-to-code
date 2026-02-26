from enum import StrEnum

from pydantic import BaseModel


class ApplicationCode(StrEnum):
    """The list of applications that will leveraging Augmentation functionality."""

    TEXT_TO_CODE = "text-to-code"


class ReturnCode(StrEnum):
    """Return code."""

    SUCCESS = "success"
    FAILURE = "failure"


class Metadata(BaseModel):
    """Model to hold augmentation metadata."""

    original_eicr_id: str
    augmented_eicr_id: str
