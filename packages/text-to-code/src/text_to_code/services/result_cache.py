from hashlib import sha256

from opensearchpy import OpenSearch

from lambda_handler.models import OpenSearchResult
from shared_models import Code
from text_to_code.models.result_cache import OpenSearchResultCacheSource


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
    """
    response = opensearch_client.get(index=index, id=os_doc_id)
    if response and response["found"]:
        return response["source"]
    return None


def put_new_cached_result(  # noqa: PLR0913
    opensearch_client: OpenSearch,
    index: str,
    candidate_input: str,
    data_field: str,
    loinc_code: Code,
    search_score: float,
    reranker_score: float,
    opensearch_retrieved_results: OpenSearchResult,
    reranker_processed_results: list,
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
    :param opensearch_retrieved_results: The collection of results returned by OpenSearch
      during the original processing of this input.
    :param reranker_processed_results: The list of ScoredResult objects produced by the
      reranker during original processing.
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
        loinc_code=loinc_code,
        search_score=search_score,
        reranker_score=reranker_score,
        opensearch_retrieved_results=opensearch_retrieved_results,
        reranker_processed_results={"results": reranker_processed_results},
    )
    put_response = opensearch_client.index(index=index, id=cache_key, body=new_cache_hit)
    return put_response["result"] == "created"
