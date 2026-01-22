from enum import StrEnum

from pydantic import BaseModel


class EicrDataField(StrEnum):
    """Enum for eICR data fields relevant to the TTC module."""

    LAB_TEST_NAME_RESULTED = "Lab Test Name Resulted"
    LAB_TEST_NAME_ORDERED = "Lab Test Name Ordered"


class Candidate(BaseModel):
    """Model representing a piece of text to be considered for encoding."""

    value: str
    xpath: str
