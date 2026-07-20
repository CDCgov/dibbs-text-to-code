from opensearchpy import OpenSearch

from lambda_handler.models import (
    OpenSearchHit,
    OpenSearchHits,
    OpenSearchHitSource,
    OpenSearchResult,
    OpenSearchShards,
)
from shared_models import Code
from text_to_code.models.result_cache import OpenSearchResultCacheSource
from text_to_code.services.utils import compute_cache_key


def _parse_cache_source(response_source: dict) -> OpenSearchResultCacheSource:
    """Parse a cache document's ``_source`` body into a structured object.

    :param response_source: The ``_source`` dictionary from an OpenSearch GET or
      mget document response.
    :returns: The Source of the OpenSearch Cache Result, expressed as a structured
      object.
    """
    response_loinc = response_source["loinc_code"]
    opensearch_results = response_source["opensearch_retrieved_scores"]

    opensearch_retrieved_scores = OpenSearchResult(
        took=opensearch_results["took"],
        timed_out=opensearch_results["timed_out"],
        _shards=OpenSearchShards(
            total=opensearch_results["_shards"]["total"],
            successful=opensearch_results["_shards"]["successful"],
            skipped=opensearch_results["_shards"]["skipped"],
            failed=opensearch_results["_shards"]["failed"],
        ),
        hits=OpenSearchHits(
            total=opensearch_results["hits"]["total"],
            hits=[
                OpenSearchHit(
                    _index=hit["_index"],
                    _id=hit["_id"],
                    _score=hit["_score"],
                    _source=OpenSearchHitSource(
                        id=hit["_source"]["id"],
                        loinc_code=hit["_source"]["loinc_code"],
                        loinc_name_type=hit["_source"]["loinc_name_type"],
                        description=hit["_source"]["description"],
                        loinc_type=hit["_source"]["loinc_type"],
                    ),
                )
                for hit in opensearch_results["hits"]["hits"]
            ],
        ),
    )

    return OpenSearchResultCacheSource(
        cache_key=response_source["cache_key"],
        text=response_source["text"],
        data_field=response_source["data_field"],
        loinc_code=Code(
            code=response_loinc["code"],
            code_system=response_loinc["code_system"],
            code_system_name=response_loinc["code_system_name"],
            display_name=response_loinc["display_name"],
            original_text=response_loinc["original_text"],
        ),
        search_score=response_source["search_score"],
        reranker_score=response_source["reranker_score"],
        opensearch_retrieved_scores=opensearch_retrieved_scores,
        reranker_processed_results=response_source["reranker_processed_results"],
        cached_at=response_source["cached_at"],
    )


def get_cached_result(
    opensearch_client: OpenSearch, index: str, os_doc_id: str
) -> OpenSearchResultCacheSource | None:
    """Queries an OpenSearch Index by document ID.

    Full details of the OpenSearch API's GET Response body can be found at
    https://docs.opensearch.org/latest/api-reference/document-apis/get-documents/#response-body-fields

    :param opensearch_client: An instantiated client meant for communicating with
      the TTC OpenSearch instance.
    :param index: The namespace of the Index to check.
    :param os_doc_id: The OpenSearch document `_id` parameter to check for.
    :returns: The Source of the OpenSearch Cache Result, expressed as a structured
      object.
    """
    response = opensearch_client.get(index=index, id=os_doc_id, ignore=404)
    if response and response["found"]:
        return _parse_cache_source(response["_source"])

    return None


def get_cached_results(
    opensearch_client: OpenSearch, index: str, os_doc_ids: list[str]
) -> dict[str, OpenSearchResultCacheSource | None]:
    """Queries an OpenSearch Index for several document IDs in one mget call.

    A single mget replaces one GET round trip per document, which matters when
    a record produces several candidates to look up.

    :param opensearch_client: An instantiated client meant for communicating with
      the TTC OpenSearch instance.
    :param index: The namespace of the Index to check.
    :param os_doc_ids: The OpenSearch document `_id` parameters to check for.
    :returns: A mapping of each requested document ID to its parsed cache source,
      or None for IDs with no cached entry.
    """
    results: dict[str, OpenSearchResultCacheSource | None] = dict.fromkeys(os_doc_ids)
    if not os_doc_ids:
        return results

    # ignore=404 mirrors get_cached_result: a missing cache index is an
    # all-miss, not an error.
    response = opensearch_client.mget(body={"ids": list(results)}, index=index, ignore=404)
    for doc in (response or {}).get("docs", []):
        if doc.get("found"):
            results[doc["_id"]] = _parse_cache_source(doc["_source"])

    return results


def put_new_cached_result(  # noqa: PLR0913
    opensearch_client: OpenSearch,
    index: str,
    candidate_input: str,
    data_field: str,
    loinc_code: Code,
    search_score: float,
    reranker_score: float,
    opensearch_retrieved_scores: OpenSearchResult,
    reranker_processed_results: list,
    cache_key: str | None = None,
) -> bool:
    """Stores a hit for a new nonstandard input in the Result Cache index in OpenSearch.

    Full API documentation for the `.index()` method can be found at
    https://docs.opensearch.org/latest/api-reference/document-apis/index-document/.

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
    :param opensearch_retrieved_scores: The collection of results returned by OpenSearch
      during the original processing of this input.
    :param reranker_processed_results: The list of ScoredResult objects produced by the
      reranker during original processing.
    :param cache_key: The precomputed cache key for this input, if the caller already
      computed it for the lookup; recomputed from the input when omitted.
    :returns: A boolean indicating whether the new cache hit was successfully added to
      the OpenSearch index.
    """
    cache_key = cache_key or compute_cache_key(candidate_input, data_field)
    new_cache_hit: OpenSearchResultCacheSource = OpenSearchResultCacheSource(
        cache_key=cache_key,
        text=candidate_input,
        data_field=data_field,
        loinc_code=loinc_code,
        search_score=search_score,
        reranker_score=reranker_score,
        opensearch_retrieved_scores=opensearch_retrieved_scores,
        reranker_processed_results={"results": reranker_processed_results},
    )
    put_response = opensearch_client.index(
        index=index, id=cache_key, body=new_cache_hit.model_dump(by_alias=True)
    )
    return put_response["result"] == "created"
