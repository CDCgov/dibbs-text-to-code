from pydantic import BaseModel
from pydantic import Field


class S3Location(BaseModel):
    """Represents the location of a file in S3, indicating which file contained the relevant data."""

    bucket: str = Field(description="The S3 bucket where the file is located.")
    key: str = Field(description="The S3 key (path) where the file is located.")


class OpenSearchHitSource(BaseModel):
    """Represents a single search result _source returned from OpenSearch."""

    id: int = Field(description="The unique ID from the embedding data of the search result hit.")
    loinc_code: str = Field(description="The LOINC code of the search result hit.")
    loinc_name_type: str = Field(description="The LOINC name type of the search result hit.")
    description: str = Field(description="The description of the search result hit.")
    loinc_type: str = Field(description="The LOINC type of the search result hit.")
    s3: S3Location = Field(description="The S3 location of the search result hit.")


class OpenSearchHit(BaseModel):
    """Represents a single search result hit returned from OpenSearch."""

    index: str = Field(
        description="The index that the search result hit came from.", alias="_index"
    )
    id: str = Field(description="The unique OpenSearch ID of the search result hit.", alias="_id")
    score: float = Field(
        description="The cosine similarity score of the search result hit.", alias="_score"
    )
    source: OpenSearchHitSource = Field(
        description="The source of the search result hit.", alias="_source"
    )


class OpenSearchHits(BaseModel):
    """Represents all of the search result hits returned from OpenSearch."""

    total_hits: dict[str, int] = Field(
        alias="total", description="The total number of hits returned from OpenSearch."
    )
    hits: list[OpenSearchHit] = Field(
        description="The list of search result hits returned from OpenSearch."
    )


class OpenSearchShards(BaseModel):
    """Represents the shard information returned from OpenSearch."""

    total: int = Field(description="The total number of shards involved in the search.")
    successful: int = Field(description="The number of shards that successfully returned results.")
    skipped: int = Field(description="The number of shards that were skipped during the search.")
    failed: int = Field(description="The number of shards that failed to return results.")


class OpenSearchResult(BaseModel):
    """Represents the overall search result returned from OpenSearch, including hits and shard information."""

    took: int = Field(description="The time taken to execute the search in milliseconds.")
    timed_out: bool = Field(description="Indicates whether the search timed out.")
    shards: OpenSearchShards = Field(
        description="The shard information for the search.", alias="_shards"
    )
    hits: OpenSearchHits = Field(description="The search result hits returned from OpenSearch.")
