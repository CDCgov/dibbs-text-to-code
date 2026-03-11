from pydantic import BaseModel


class OpenSearchResults(BaseModel):
    """Model for OpenSearch results."""

    total_hits: int
    """The total number of hits returned by the OpenSearch query."""

    hits: list[dict]
    """The list of hits returned by the OpenSearch query."""
