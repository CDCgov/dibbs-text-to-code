from enum import Enum
from typing import Annotated

from pydantic import BaseModel
from pydantic.types import StringConstraints


class CodeTypes(Enum):
    """Type of codes TTC will attempt to standardize."""

    LAB_ORDER = "lab_order"
    LAB_RESULT = "lab_result"


class Candidate(BaseModel):
    """Model representing a piece of text to be considered for encoding."""

    value: Annotated[str, StringConstraints(min_length=3)]
    xpath: str


class ProblematicField(BaseModel):
    """Model representing problematic coding."""

    code_type: CodeTypes
    context: str
