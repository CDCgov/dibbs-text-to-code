from collections.abc import Callable

import numpy as np
from sentence_transformers import CrossEncoder
from typing_extensions import TypedDict

from text_to_code.models.registry import HIGH_SCORE, LOW_SCORE, MAX_MARGIN, MIN_MARGIN, TTC_RERANKER
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


def rerank(
    nonstandard_in: str,
    scores: list[float],
    hits: list[str],
) -> list[ScoredResult]:
    """Re-sorts hits by cross-encoder score values.

    Given a list of text strings returned from OpenSearch, prune the results
    using the adaptive margin, then score and sort the remaining search hits
    using the Text-to-Code system's default Reranker model.
    The model will generate a cross-encoding score value measuring each
    search result's information similarity to the original nonstandard input.

    :param nonstandard_in: The original narrative free-text input to TTC.
    :param scores: The list of OpenSearch result scores, already sorted in descending order.
    :param hits: The list of OpenSearch results, in text string form.
    :returns: A list of dictionaries representing the newly cross-encoder
      scored search results, sorted in descending order of score.
    """
    pruned_hits = _prune(scores, hits)
    ranks = _RERANKER.rank(nonstandard_in, pruned_hits)
    sorted_ranks: list[ScoredResult] = [
        {"code_string": pruned_hits[r["corpus_id"]], "score": r["score"]} for r in ranks
    ]
    return sorted_ranks


def _within_margin(scores: list[float], margin: float) -> int:
    """Determines how many candidates are within a margin of the top score.

    :param scores: Retriever scores sorted in descending order.
    :param margin: Allowed difference from the top retriever score.
    :returns: Number of retriever candidates within the given margin.
    """
    if scores is None or len(scores) <= 1:
        return 0

    top = scores[0]

    return sum(top - score <= margin for score in scores[1:])


def _create_margin_fn(
    low_score: float = LOW_SCORE,
    high_score: float = HIGH_SCORE,
    max_margin: float = MAX_MARGIN,
    min_margin: float = MIN_MARGIN,
) -> Callable[[float], float]:
    """Create a margin function interpolating between max and min margins.

    Based on the given score, low_score, and high_score, as the retriever
    confidence increases, the allowable margin gets smaller.

    :param score: The top retriever score for which to calculate the margin.
    :param low_score: The lowest score in the retriever results.
    :param high_score: The highest score in the retriever results.
    :param max_margin: The maximum allowable margin.
    :param min_margin: The minimum allowable margin.
    :returns: A function that takes a score and returns the
        interpolated margin.

    """

    def margin(score: float) -> float:
        """Interpolates the margin based on the score.

        :param score: The retriever score for which to calculate the margin.
        :returns: The interpolated margin based on the score.
        """
        x = np.clip(
            (score - low_score) / (high_score - low_score),
            0,
            1,
        )

        return max_margin + x * (min_margin - max_margin)

    return margin


def _prune(scores: list[float], texts: list[str]) -> list[str]:
    """Removes any results not within the given margin of the top score.

    :param scores: The list of search result scores, already sorted in descending order.
    :param texts: The list of search result texts corresponding to the scores.
    :returns: A list of texts representing the search results that are within the margin of the top score.
    """
    if not scores or not texts:
        return []

    top_score = scores[0]

    margin_fn = _create_margin_fn(
        low_score=LOW_SCORE,
        high_score=HIGH_SCORE,
        max_margin=MAX_MARGIN,
        min_margin=MIN_MARGIN,
    )

    adaptive_margin = margin_fn(top_score)
    num_within_margin = _within_margin(scores, adaptive_margin)
    pruned_results = texts[: num_within_margin + 1]  # add 1 to include the top score
    return pruned_results
