from datetime import UTC, datetime

from pydantic import Field

from lambda_handler.models import OpenSearchResult
from shared_models import Code, FrozenBaseModel


class OpenSearchResultCacheSource(FrozenBaseModel):
    """Represents a term-standardization mapping returned from the OpenSearch Result Cache Index."""

    cache_key: str = Field(
        description="The computed hash key mapping candidate text + data field to this known hit."
    )
    text: str = Field(description="The input candidate text this Cache Result is associated with.")
    data_field: str = Field(
        description="The data field from which the candidate text was retrieved during initial "
        "processing of this cache hit."
    )
    loinc_code: Code = Field(description="The Code object for this cached input.")
    search_score: float = Field(
        description="The cosine similarity score calculated for this standardization during "
        "initial processing of this input."
    )
    reranker_score: float = Field(
        description="The cross-encoder score calculated for this standardization during initial "
        "processing of this input."
    )
    opensearch_retrieved_scores: OpenSearchResult = Field(
        description="The serialized list of OpenSearch results returned during the initial "
        "processing of this input, as a JSON dict."
    )
    reranker_processed_results: dict = Field(
        description="The serialized list of ScoredResult objects calculated by the Reranker "
        "during initial processing of this input, as a JSON dict. Note that the value used "
        "by the TTC Lambda is a single list, so this object will always have just a single "
        "key `results`."
    )
    cached_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="The timestamp at which this input was cached.",
    )


class OpenSearchGetResponse(FrozenBaseModel):
    """Represents the response body returned by an ID-indexed GET request to the OpenSearch API."""

    index: str = Field(description="The name of the index containing the document.", alias="_index")
    id: str = Field(description="The document's unique identifier.", alias="_id")
    version: int = Field(
        description="The document's version number, incremented each time the document is updated",
        alias="_version",
    )
    seq_no: int = Field(
        description="The sequence number assigned to the document for the indexing operation. "
        "Used to ensure an older version doesn't overwrite a newer version.",
        alias="_seq_no",
    )
    primary_term: int = Field(
        description="The primary term assigned to the document for the indexing operation. "
        "Used with `seq_no` for optimistic concurrency control.",
        alias="_primary_term",
    )
    found: bool = Field(
        description="Indicates whether the document exists (`True` if it was found) in the "
        "searched index. For searches against the `result-cache` index, the 'document' will be "
        "a cache-key pair whose source data contains the known standardized LOINC code."
    )
    routing: str = Field(
        description="The routing value used to determine which shard stores the document. "
        "Only included if a routing value was specified when the document was indexed.",
        alias="_routing",
    )
    source: OpenSearchResultCacheSource = Field(description="The cached result for the input.")
    fields: dict[str, list] = Field(
        description="Stored field values of the mappings.", alias="_fields"
    )
