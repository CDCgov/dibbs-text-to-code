from typing import Annotated

from pydantic import BaseModel
from pydantic.types import StringConstraints


class Candidate(BaseModel):
    """Model representing a piece of text to be considered for encoding."""

    value: Annotated[str, StringConstraints(min_length=3)]
    xpath: str
