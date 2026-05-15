import json
from datetime import UTC
from datetime import datetime
from hashlib import sha256

from opensearchpy import OpenSearch
from pydantic import Field

from shared_models import Code
from shared_models import FrozenBaseModel


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
    loinc_code: str = Field(description="The serialized Code object for this cached input.")
    search_score: float = Field(
        description="The cosine similarity score calculated for this standardization during "
        "initial processing of this input."
    )
    reranker_score: float = Field(
        description="The cross-encoder score calculated for this standardization during initial "
        "processing of this input."
    )
    cached_at: str = Field(description="The timestamp at which this input was cached.")


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
        description="Indicates whether the document exists (`True` if it was found)."
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


def get_cached_result(
    opensearch_client: OpenSearch, index: str, os_doc_id: str
) -> OpenSearchResultCacheSource | None:
    """Queries an OpenSearch Index by document ID.

    :param opensearch_client: An instantiated client meant for communicating with
      the TTC OpenSearch instance.
    :param index: The namespace of the Index to check.
    :param os_doc_id: The OpenSearch document `_id` parameter to check for.
    """
    response = opensearch_client.get(index=index, id=os_doc_id)
    if response and response["found"]:
        return response["source"]
    return None


def put_new_cached_result(
    opensearch_client: OpenSearch,
    index: str,
    candidate_input: str,
    data_field: str,
    loinc_code: Code,
    search_score: float,
    reranker_score: float,
) -> bool:
    """Stores a hit for a new nonstandard input in the Result Cache index in OpenSearch.

    :param opensearch_client: An instantiated client for communicating with OpenSearch.
    :param index: The index name to store the cache hit in.
    :param candidate_input: The candidate text extracted from a schematron error that
      was used as the input for OpenSearch semantic similarity.
    :param data_field: The data field associated with the candidate text in the eICR.
    :param loinc_code: A LOINC code object representing the nonstandard input's correct
      standardization, including display name and numeric code.
    :param search_score: The cosine similarity score returned by OpenSearch during
      embedding comparisons.
    :param reranker_score: The cross-encoder score calculated by the reranker during
      final decision making on this input.
    :returns: A boolean indicating whether the new cache hit was successfully added to
      the OpenSearch index.
    """
    cache_key = sha256(
        (candidate_input.strip().lower() + "|" + data_field).encode("utf-8")
    ).hexdigest()
    new_cache_hit: OpenSearchResultCacheSource = OpenSearchResultCacheSource(
        cache_key=cache_key,
        text=candidate_input,
        data_field=data_field,
        loinc_code=json.dumps(loinc_code.__dict__),
        search_score=search_score,
        reranker_score=reranker_score,
        cached_at=datetime.now(UTC).isoformat(),
    )
    put_response = opensearch_client.index(index=index, id=cache_key, body=new_cache_hit)
    return put_response["result"] == "created"
