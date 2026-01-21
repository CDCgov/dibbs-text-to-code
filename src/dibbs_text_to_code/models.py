from pydantic import BaseModel


class Candidate(BaseModel):
    """Model representing a piece of text to be considered for encoding."""

    value: str
    xpath: str
