"""Core text-to-code matching: embed -> KNN search -> rerank -> top LOINC code.

This is the single implementation of the matching step shared by the async SQS
pipeline (``lambda_function.py``) and the synchronous demo API (``service.py``).
The pipeline needs the intermediate retrieval artifacts for its metadata and
result cache, so the outcome carries them alongside the matched ``Code``.
"""

from dataclasses import dataclass

from opensearchpy import OpenSearch

import lambda_handler
from lambda_handler.models import OpenSearchResult
from shared_models import LOINC_NAME, LOINC_OID, Code, DataField
from text_to_code.models import query as query_models
from text_to_code.services.embedder import embed
from text_to_code.services.query import QueryBuilder
from text_to_code.services.reranker import ScoredResult, rerank

NO_HITS_MESSAGE = "Opensearch query returned no hits."
NO_RERANK_RESULTS_MESSAGE = "Reranker did not return any results."


@dataclass(frozen=True)
class Match:
    """A successful match, including the retrieval intermediates behind it."""

    code: Code
    opensearch_results: OpenSearchResult
    ranked_results: list[ScoredResult]
    top_retriever_score: float


@dataclass(frozen=True)
class NoMatch:
    """A failed matching attempt and how far retrieval got before it stopped.

    ``ranked_results`` is ``None`` when reranking never ran (no hits).
    """

    opensearch_results: OpenSearchResult
    ranked_results: list[ScoredResult] | None
    unmatched_reason: str


def match_text(
    text: str,
    data_field: DataField,
    opensearch_client: OpenSearch,
    index: str,
) -> Match | NoMatch:
    """Map a raw text string to its best LOINC ``Code``.

    Embeds the text, runs the KNN query against ``index``, reranks the hits, and
    selects the top-ranked result.

    :param text: The raw clinical text to standardize (e.g. "Glucose measurement").
    :param data_field: The data field that determines the LOINC type filter.
    :param opensearch_client: An OpenSearch client used for the KNN query.
    :param index: The OpenSearch index to query.
    :return: The matching outcome, with or without a matched ``Code``.
    """
    vector_embedding = embed(text)
    vector_parameters = query_models.VectorSearchParams(
        vector=vector_embedding.tolist(), data_field=data_field
    )
    query = QueryBuilder().with_vector_search(vector_parameters).build()

    opensearch_results = lambda_handler.retrieve_opensearch_results(
        query=query, index=index, opensearch_client=opensearch_client
    )

    hits = opensearch_results.hits.hits
    if not hits:
        return NoMatch(
            opensearch_results=opensearch_results,
            ranked_results=None,
            unmatched_reason=NO_HITS_MESSAGE,
        )

    ranked_results = rerank(text, [hit.source.description for hit in hits])
    if not ranked_results:
        return NoMatch(
            opensearch_results=opensearch_results,
            ranked_results=ranked_results,
            unmatched_reason=NO_RERANK_RESULTS_MESSAGE,
        )

    top_result = next(
        hit for hit in hits if hit.source.description == ranked_results[0]["code_string"]
    )
    code = Code(
        code=top_result.source.loinc_code,
        code_system=LOINC_OID,
        code_system_name=LOINC_NAME,
        display_name=top_result.source.description,
        original_text=text,
    )
    return Match(
        code=code,
        opensearch_results=opensearch_results,
        ranked_results=ranked_results,
        top_retriever_score=top_result.score,
    )
