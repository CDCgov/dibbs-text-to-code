from sentence_transformers import CrossEncoder
from typing_extensions import TypedDict

from text_to_code.models.registry import TTC_RERANKER
from text_to_code.services.utils import get_model_info

_RERANKER = CrossEncoder(TTC_RERANKER)
RERANKER_MODEL_INFO = get_model_info(TTC_RERANKER)


class ScoredResult(TypedDict):
    """The search result with its score."""

    code_string: str
    """
    This is the code's display name.
    """
    score: float


def rerank(nonstandard_in: str, hits: list[str]) -> list[ScoredResult]:
    """Re-sorts hits by cross-encoder score values.

    Given a list of text strings returned from OpenSearch, score and sort
    the search hits using the Text-to-Code system's default Reranker model.
    The model will generate a cross-encoding score value measuring each
    search result's information similarity to the original nonstandard input.

    :param nonstandard_in: The original narrative free-text input to TTC.
    :param hits: The list of OpenSearch results, in text string form.
    :returns: A list of dictionaries representing the newly cross-encoder
      scored search results, sorted in descending order of score.
    """
    ranks = _RERANKER.rank(nonstandard_in, hits)
    sorted_ranks: list[ScoredResult] = [
        {"code_string": hits[r["corpus_id"]], "score": r["score"]} for r in ranks
    ]
    return sorted_ranks
