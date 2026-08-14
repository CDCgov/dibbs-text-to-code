import pytest

from text_to_code.models.registry import HIGH_SCORE, LOW_SCORE, MAX_MARGIN, MIN_MARGIN
from text_to_code.services.reranker import (
    ScoredResult,
    create_margin_fn,
    prune,
    rerank,
    within_margin,
)


class TestReranker:
    def test_reranker_empty_hits(self) -> None:
        ranks = rerank("Influenza virus A and B and SARS-CoV-2 (COVID-19)", [])
        assert len(ranks) == 0

    def test_reranker_single_search_result(self) -> None:
        ranks = rerank(
            "Influenza virus A and B and SARS-CoV-2 (COVID-19)",
            ["Influenza virus A and B and SARS-CoV-2 (COVID-19)"],
        )
        ranks: list[ScoredResult] = [
            {"code_string": r["code_string"], "score": round(float(r["score"]), 3)} for r in ranks
        ]
        assert ranks == [
            {"code_string": "Influenza virus A and B and SARS-CoV-2 (COVID-19)", "score": 0.99}
        ]

    def test_reranker_multiple_hits(self) -> None:
        nonstandard_in = "albumin/creatinine ratio (acr)"
        search_hits = [
            "Albumin/Creatinine [Ratio] in Urine",
            "Albumin/Creatinine (U) [Mass ratio]",
            "Albumin/Creatinine [Ratio] in 24 hour Urine",
            "Albumin/Creatinine (U) [Molar ratio]",
        ]
        ranks = rerank(nonstandard_in, search_hits)
        ranks: list[ScoredResult] = [
            {"code_string": r["code_string"], "score": round(float(r["score"]), 3)} for r in ranks
        ]
        assert ranks == [
            {
                "code_string": "Albumin/Creatinine [Ratio] in Urine",
                "score": 0.467,
            },
            {
                "code_string": "Albumin/Creatinine [Ratio] in 24 hour Urine",
                "score": 0.271,
            },
            {
                "code_string": "Albumin/Creatinine (U) [Mass ratio]",
                "score": 0.204,
            },
            {"code_string": "Albumin/Creatinine (U) [Molar ratio]", "score": 0.201},
        ]


@pytest.mark.parametrize(
    ("scores", "margin", "expected"),
    [
        ([], 0.1, 0),
        ([0.9], 0.1, 0),
        ([0.9, 0.85, 0.8, 0.75, 0.7], 0.1, 2),
        ([0.9, 0.85, 0.8, 0.75, 0.7], 0.05, 0),
        ([0.9, 0.85, 0.8, 0.75, 0.7], 0.2, 3),
    ],
)
class TestWithinMargin:
    def test_within_margin(self, scores, margin, expected) -> None:
        assert within_margin(scores, margin) == expected


class TestCreateMarginFn:
    def test_create_margin_fn(self) -> None:
        low_score = 0.5
        high_score = 0.9
        max_margin = 0.2
        min_margin = 0.05

        margin_fn = create_margin_fn(low_score, high_score, max_margin, min_margin)

        # Test with a score below the low_score
        assert margin_fn(0.4) == max_margin

        # Test with a score above the high_score
        margin = margin_fn(1.0)
        assert round(margin, 3) == min_margin

        # Test with a score between low_score and high_score
        assert margin_fn(0.7) == (max_margin + min_margin) / 2

    def test_create_margin_fn_with_default_values(self) -> None:
        margin_fn = create_margin_fn()

        # Test with a score below the low_score
        assert round(margin_fn(0.4), 3) == MAX_MARGIN

        # Test with a score above the high_score
        assert round(margin_fn(1.0), 3) == MIN_MARGIN

        # Test with a score between low_score and high_score
        middle_score = HIGH_SCORE - (LOW_SCORE / 5)
        margin = margin_fn(middle_score)
        assert round(margin, 3) > MIN_MARGIN
        assert round(margin, 3) < MAX_MARGIN


# @pytest.mark.parametrize(
#     ("scores", "texts", "expected"),
#     [
#         # no scores, no texts
#         ([], [], []),
#         # single score, single text
#         ([0.9], ["Result 1"], ["Result 1"]),
#     ],
# )
class TestPrune:
    def test_prune_no_scores_or_texts(self) -> None:
        scores = []
        texts = []
        expected = []
        assert prune(scores, texts) == expected

    def test_prune_single_score_and_text(self) -> None:
        scores = [0.9]
        texts = ["Result 1"]
        expected = texts
        assert prune(scores, texts) == expected

    def test_prune_multiple_scores_within_margin(self) -> None:
        scores = [0.9, 0.85, 0.8, 0.75, 0.7]
        texts = ["Result 1", "Result 2", "Result 3", "Result 4", "Result 5"]

        margin_fn = create_margin_fn(
            low_score=LOW_SCORE, high_score=HIGH_SCORE, max_margin=MAX_MARGIN, min_margin=MIN_MARGIN
        )
        margin = margin_fn(scores[0])
        num_within_margin = within_margin(scores, margin)

        assert (
            prune(scores, texts) == texts[: num_within_margin + 1]
        )  # add 1 to include the top score
