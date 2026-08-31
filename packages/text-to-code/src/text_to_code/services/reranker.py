from collections.abc import Callable
from typing import cast

import numpy as np
from sentence_transformers import CrossEncoder
from typing_extensions import TypedDict

from lambda_handler.opensearch import OpenSearchHit
from text_to_code.models.registry import (
    HIGH_RANK_THRESHOLD,
    HIGH_SCORE,
    LEADER_MARGIN,
    LOW_SCORE,
    MAX_MARGIN,
    MIN_MARGIN,
    MINIMUM_HITS_TO_HIGH_RANK,
    MINIMUM_HITS_WITHIN_MARGIN,
    TTC_RERANKER,
)
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


class RankResult(TypedDict):
    """The search result with its score and corpus id.

    This is the result returned by the Reranker model, and helps with typing
    because the type specified by SentenceTransformers' .rank() method is too
    permissive for our type checker.
    """

    corpus_id: int
    score: float
    text: str


def select_opensearch_candidate(
    nonstandard_in: str, results_list: list[OpenSearchHit]
) -> tuple[OpenSearchHit | None, list[ScoredResult]]:
    """Applies sequential heuristics to select the best standardization.

    Given a list of OpenSearch hits, this function applies a 4-case selection procedure
    to find the most suitable hit to use as Text-to-Code's standardization for a
    particular nonstandard input. The ordered case selection logic is as follows:

      1. Candidates with perfect 1.0 cosine similarities,
      2. Candidates with a leader margin sufficiently ahead of the runner-up result,
      3. The candidate chosen by the reranker model out of the list of candidates
         whose similarity scores exceed a special "high-rank" threshold, and
      4. The candidate chosen by the reranker model out of all candidates that
         survive an adaptive margin-based pruning.

    :param nonstandard_in: The original narrative free-text input to TTC.
    :param results_list: The list of OpenSearch hits, extracted from the general
      OpenSearchResult response.
    :returns: A tuple consisting of the selected candidate out of those supplied
      by the Reranker, as well as the fully-scored list of candidates that underwent
      reranking.
    """
    high_rank_results = [hit for hit in results_list if hit.score >= HIGH_RANK_THRESHOLD]
    retrieved_loinc_names = [hit.source.description for hit in results_list]
    retriever_scores = [hit.score for hit in results_list]

    selected_result = None
    use_reranker_result = True
    prune_before_ranking = True

    # Case 1: We have a leading perfect score in the OpenSearch hits, which
    # means the top candidate is a verbatim LOINC code string (either directly
    # entered, or found via auto-map). In either case, no need to rerank.
    # Ignore the ruff rule here because explicitly spelling out these cases
    # improves logic readability.
    if retriever_scores[0] >= 1.0:  # noqa: SIM114
        use_reranker_result = False
        selected_result = results_list[0]

    # Case 2: The highest scoring search result exceeds the "leader margin,"
    # meaning the sum of its similarity score _plus_ the margin by which it
    # exceeds the second highest scoring result is greater than the threshold
    # required for auto-classification. As above, we will just use the result.
    elif (
        len(retriever_scores) > 1
        and 2.0 * retriever_scores[0] - retriever_scores[1] >= LEADER_MARGIN
    ):
        use_reranker_result = False
        selected_result = results_list[0]

    # Case 3: We have enough candidates with high retriever scores to perform
    # high-threshold reranking, which performs reranking only on those
    # candidates who pass the "high-rank" threshold. Note that in this case,
    # we do not perform additional margin-based pruning.
    elif len(high_rank_results) >= MINIMUM_HITS_TO_HIGH_RANK:
        retrieved_loinc_names = [hit.source.description for hit in high_rank_results]
        retriever_scores = [hit.score for hit in high_rank_results]
        prune_before_ranking = False

    # Case 4 (Default): In the absence of a perfect match, a leader candidate,
    # or high-rank thresholding, we'll perform normal reranking using
    # adaptive margin pruning.
    ranked_results = rerank(
        nonstandard_in,
        retriever_scores,
        retrieved_loinc_names,
        use_pruning=prune_before_ranking,
    )

    if ranked_results and use_reranker_result:
        selected_result = next(
            (x for x in results_list if x.source.description == ranked_results[0]["code_string"]),
        )

    return selected_result, ranked_results


def rerank(
    nonstandard_in: str,
    scores: list[float],
    hits: list[str],
    use_pruning: bool = True,
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
    :param use_pruning: Optionally, whether to apply adaptive margin pruning
      to the OpenSearch hits. If filtering was performed (due to high-rank
      thresholding) prior to calling this function, further pruning is not
      necessary. Defaults to True.
    :returns: A list of dictionaries representing the newly cross-encoder
      scored search results, sorted in descending order of score.
    """
    pruned_hits = hits
    if use_pruning:
        pruned_hits = _prune(scores, hits)
    ranks = cast(
        list[RankResult],
        _RERANKER.rank(nonstandard_in, pruned_hits),
    )
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
    num_within_margin = max(num_within_margin, MINIMUM_HITS_WITHIN_MARGIN)
    pruned_results = texts[: num_within_margin + 1]  # add 1 to include the top score
    return pruned_results
