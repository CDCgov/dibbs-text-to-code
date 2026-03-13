import pydantic


class S3Location(pydantic.BaseModel):
    """Represents the location of a file in S3, indicating which file contained the relevant data."""

    bucket: str = pydantic.Field(description="The S3 bucket where the file is located.")
    key: str = pydantic.Field(description="The S3 key (path) where the file is located.")


class OpenSearchHitSource(pydantic.BaseModel):
    """Represents a single search result _source returned from OpenSearch."""

    id: int = pydantic.Field(
        description="The unique ID from the embedding data of the search result hit."
    )
    loinc_code: str = pydantic.Field(description="The LOINC code of the search result hit.")
    loinc_name_type: str = pydantic.Field(
        description="The LOINC name type of the search result hit."
    )
    description: str = pydantic.Field(description="The description of the search result hit.")
    loinc_type: str = pydantic.Field(description="The LOINC type of the search result hit.")
    s3: S3Location = pydantic.Field(description="The S3 location of the search result hit.")


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
