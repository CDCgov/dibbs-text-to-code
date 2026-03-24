import pydantic

from shared_models import OpenSearchHitSource


class OpenSearchHit(pydantic.BaseModel):
    """Represents a single search result hit returned from OpenSearch."""

    index: str = pydantic.Field(
        description="The index that the search result hit came from.", alias="_index"
    )
    id: str = pydantic.Field(
        description="The unique OpenSearch ID of the search result hit.", alias="_id"
    )
    score: float = pydantic.Field(
        description="The cosine similarity score of the search result hit.", alias="_score"
    )
    source: OpenSearchHitSource = pydantic.Field(
        description="The source of the search result hit.", alias="_source"
    )


class OpenSearchHits(pydantic.BaseModel):
    """Represents all of the search result hits returned from OpenSearch."""

    total_hits: dict[str, int] = pydantic.Field(
        alias="total", description="The total number of hits returned from OpenSearch."
    )
    hits: list[OpenSearchHit] = pydantic.Field(
        description="The list of search result hits returned from OpenSearch."
    )


class OpenSearchShards(pydantic.BaseModel):
    """Represents the shard information returned from OpenSearch."""

    total: int = pydantic.Field(description="The total number of shards involved in the search.")
    successful: int = pydantic.Field(
        description="The number of shards that successfully returned results."
    )
    skipped: int = pydantic.Field(
        description="The number of shards that were skipped during the search."
    )
    failed: int = pydantic.Field(description="The number of shards that failed to return results.")


class OpenSearchResult(pydantic.BaseModel):
    """Represents the overall search result returned from OpenSearch, including hits and shard information."""

    took: int = pydantic.Field(description="The time taken to execute the search in milliseconds.")
    timed_out: bool = pydantic.Field(description="Indicates whether the search timed out.")
    shards: OpenSearchShards = pydantic.Field(
        description="The shard information for the search.", alias="_shards"
    )
    hits: OpenSearchHits = pydantic.Field(
        description="The search result hits returned from OpenSearch."
    )
