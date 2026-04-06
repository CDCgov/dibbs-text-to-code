from sentence_transformers import CrossEncoder

from shared_models import SortedRank
from text_to_code.models.registry import TTC_RERANKER

_RERANKER = CrossEncoder(TTC_RERANKER)


class Reranker:
    """Scores and sorts OpenSearch results."""

    def rerank(self, nonstandard_in: str, hits: list[str]) -> list[SortedRank]:
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
        sorted_ranks: list[SortedRank] = [
            {"code_string": hits[r["corpus_id"]], "score": r["score"]} for r in ranks
        ]
        return sorted_ranks
