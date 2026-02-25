from enum import StrEnum

from pydantic import BaseModel
from pydantic import ConfigDict


class DataField(StrEnum):
    """Enum for eICR data fields relevant to the TTC module."""

    LAB_TEST_NAME_RESULTED = "Lab Test Name Resulted"
    LAB_TEST_NAME_ORDERED = "Lab Test Name Ordered"


class TTCAugmentation(BaseModel):
    """Model with everything needed to modify a code."""

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    location: str
    data_type: DataField
    code: str
    display_name: str
    original_text: str


class TTCAugmenterInput(BaseModel):
    """Input for the augmentation service."""

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )
    eicr_id: str
    augmentations: list[TTCAugmentation]
