"""Synchronous text-to-code service.

Maps a single raw clinical text string (e.g. a nonstandard lab test name) to a
standardized LOINC code by reusing the core Text-to-Code pipeline
(embed -> KNN search -> rerank). Unlike ``lambda_function.py``, this path takes a
plain string directly and skips all eICR XML parsing and candidate selection.

Both the Lambda Function URL handler (``api_handler.py``) and the local FastAPI
dev server (``local_server.py``) call into this module so the matching logic
lives in exactly one place.
"""

import os

from aws_lambda_powertools import Logger
from opensearchpy import OpenSearch

import lambda_handler
from shared_models import LOINC_NAME, LOINC_OID, Code, DataField
from text_to_code.models import query as query_models
from text_to_code.services.embedder import embed, embed_batch
from text_to_code.services.query import QueryBuilder
from text_to_code.services.reranker import select_opensearch_candidate

logger = Logger(service="ttc-api", child=True)

OPENSEARCH_INDEX = os.getenv("OPENSEARCH_INDEX", "ttc-index")

# The demo UI sends a single "Lab test name" element. Ordered vs. Resulted only
# changes the OpenSearch `loinc_type` terms filter, so default to Ordered and
# let callers override per request.
DEFAULT_DATA_FIELD = DataField.LAB_TEST_NAME_ORDERED


def parse_data_field(value: str | None) -> DataField:
    """Resolve a request's data-field string to a ``DataField``.

    :param value: The raw data-field string from the request, or ``None``.
    :return: The matching ``DataField``, or ``DEFAULT_DATA_FIELD`` when the value
      is missing or unrecognized.
    """
    if not value:
        return DEFAULT_DATA_FIELD
    try:
        return DataField(value)
    except ValueError:
        logger.warning(
            "Unrecognized data_field; using default",
            data_field=value,
            status="fallback",
        )
        return DEFAULT_DATA_FIELD


def code_for_text(
    text: str,
    data_field: DataField,
    opensearch_client: OpenSearch,
    index: str = OPENSEARCH_INDEX,
    *,
    embedding: list[float] | None = None,
) -> Code | None:
    """Map a single raw text string to its best LOINC ``Code``.

    Mirrors the inner matching logic of ``_process_record_pipeline`` in
    ``lambda_function.py``, but operates on a plain string instead of an eICR
    candidate: embed the text, run the KNN query, rerank the hits, and return the
    top result as a ``Code``.

    :param text: The raw clinical text to standardize (e.g. "Glucose measurement").
    :param data_field: The data field that determines the LOINC type filter.
    :param opensearch_client: An OpenSearch client used for the KNN query.
    :param index: The OpenSearch index to query.
    :param embedding: A precomputed embedding for ``text`` (from a batched encode);
      computed on the fly when omitted.
    :return: The top-ranked LOINC ``Code``, or ``None`` when there is no match.
    """
    if embedding is None:
        embedding = embed(text).tolist()
    vector_parameters = query_models.VectorSearchParams(vector=embedding, data_field=data_field)
    query = QueryBuilder().with_vector_search(vector_parameters).build()

    opensearch_results = lambda_handler.retrieve_opensearch_results(
        query=query, index=index, opensearch_client=opensearch_client
    )

    hits = opensearch_results.hits.hits
    if not hits:
        logger.info("OpenSearch returned no hits", status="no_match")
        return None

    top_result, ranked_results = select_opensearch_candidate(text, hits)

    if not top_result or not ranked_results:
        logger.info("Reranker returned no results", status="no_match")
        return None

    return Code(
        code=top_result.source.loinc_code,
        code_system=LOINC_OID,
        code_system_name=LOINC_NAME,
        display_name=top_result.source.description,
        original_text=text,
    )


def _to_result(text: str, code: Code | None) -> dict:
    """Shape a ``Code`` (or a miss) into a JSON-serializable result row."""
    if code is None:
        return {
            "input": text,
            "matched": False,
            "code": None,
            "code_system": None,
            "code_system_name": None,
            "display_name": None,
        }
    return {
        "input": text,
        "matched": True,
        "code": code.code,
        "code_system": code.code_system,
        "code_system_name": code.code_system_name,
        "display_name": code.display_name,
    }


def results_for_inputs(
    inputs: list[str],
    data_field: DataField,
    opensearch_client: OpenSearch,
    index: str = OPENSEARCH_INDEX,
) -> list[dict]:
    """Run a batch of inputs through TTC, preserving input order.

    Blank/whitespace-only inputs are returned as unmatched without querying.
    All non-blank inputs are embedded in a single batched encode call before
    the per-input search and rerank.

    :param inputs: The raw clinical text strings to standardize.
    :param data_field: The data field that determines the LOINC type filter.
    :param opensearch_client: An OpenSearch client used for the KNN query.
    :param index: The OpenSearch index to query.
    :return: One result dict per input, in the same order.
    """
    results: list[dict] = [_to_result(text, None) for text in inputs]
    pending = [(i, text) for i, text in enumerate(inputs) if text and text.strip()]
    if not pending:
        return results

    embeddings = embed_batch([text for _, text in pending])
    for (i, text), vector in zip(pending, embeddings, strict=True):
        results[i] = _to_result(
            text,
            code_for_text(text, data_field, opensearch_client, index, embedding=vector.tolist()),
        )
    return results
