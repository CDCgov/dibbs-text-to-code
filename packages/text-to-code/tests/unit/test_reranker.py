import pytest

from text_to_code.models.registry import HIGH_SCORE, LOW_SCORE, MAX_MARGIN
from text_to_code.services.reranker import ScoredResult, rerank


class TestReranker:
    def test_reranker_empty_hits(self) -> None:
        ranks = rerank("Influenza virus A and B and SARS-CoV-2 (COVID-19)", [], [])
        assert len(ranks) == 0

    def test_reranker_single_search_result(self) -> None:
        ranks = rerank(
            "Influenza virus A and B and SARS-CoV-2 (COVID-19)",
            [HIGH_SCORE],
            ["Influenza virus A and B and SARS-CoV-2 (COVID-19)"],
        )
        ranks: list[ScoredResult] = [
            {"code_string": r["code_string"], "score": r["score"]} for r in ranks
        ]
        assert ranks == [
            {
                "code_string": "Influenza virus A and B and SARS-CoV-2 (COVID-19)",
                "score": pytest.approx(0.2510499656200409, abs=1e-6),
            }
        ]

    def test_reranker_multiple_hits(self) -> None:
        nonstandard_in = "albumin/creatinine ratio (acr)"
        search_hits = [
            "Albumin/Creatinine [Ratio] in Urine",
            "Albumin/Creatinine (U) [Mass ratio]",
            "Albumin/Creatinine [Ratio] in 24 hour Urine",
            "Albumin/Creatinine (U) [Molar ratio]",
        ]
        scores = [HIGH_SCORE] * len(search_hits)
        ranks = rerank(nonstandard_in, scores, search_hits)
        ranks: list[ScoredResult] = [
            {"code_string": r["code_string"], "score": r["score"]} for r in ranks
        ]
        assert ranks == [
            {
                "code_string": "Albumin/Creatinine [Ratio] in Urine",
                "score": pytest.approx(0.00029876516782678664, abs=1e-6),
            },
            {
                "code_string": "Albumin/Creatinine [Ratio] in 24 hour Urine",
                "score": pytest.approx(0.00025727905449457467, abs=1e-6),
            },
            {
                "code_string": "Albumin/Creatinine (U) [Mass ratio]",
                "score": pytest.approx(0.00025398150319233537, abs=1e-6),
            },
            {
                "code_string": "Albumin/Creatinine (U) [Molar ratio]",
                "score": pytest.approx(0.00023938287631608546, abs=1e-6),
            },
        ]

    def test_reranker_prunes_hits_outside_margin(self) -> None:
        nonstandard_in = "Influenza virus A and B and SARS-CoV-2 (COVID-19)"
        scores = [
            LOW_SCORE,
            LOW_SCORE - (MAX_MARGIN / 3.0),
            LOW_SCORE - (MAX_MARGIN / 2.0),
            LOW_SCORE - (MAX_MARGIN * 2),
        ]
        search_hits = [
            "Influenza virus A and B and SARS-CoV-2 (COVID-19)",
            "Result Inside Margin",
            "Result Inside Margin",
            "Result Outside Margin",
        ]

        ranks = rerank(nonstandard_in, scores, search_hits)
        ranks: list[ScoredResult] = [
            {"code_string": r["code_string"], "score": r["score"]} for r in ranks
        ]

        assert ranks == [
            {
                "code_string": "Influenza virus A and B and SARS-CoV-2 (COVID-19)",
                "score": pytest.approx(0.2510499656200409, abs=2e-6),
            },
            {
                "code_string": "Result Inside Margin",
                "score": pytest.approx(0.000271708413493, abs=2e-6),
            },
            {
                "code_string": "Result Inside Margin",
                "score": pytest.approx(0.000271708413493, abs=2e-6),
            },
        ]

    def test_reranker_adds_hit_if_margin_prunes_too_many(self) -> None:
        nonstandard_in = "Influenza virus A and B and SARS-CoV-2 (COVID-19)"
        scores = [
            LOW_SCORE,
            LOW_SCORE - (MAX_MARGIN * 2),
            LOW_SCORE - (MAX_MARGIN * 3),
        ]
        search_hits = [
            "Influenza virus A and B and SARS-CoV-2 (COVID-19)",
            "Result outside margin that will be added back in",
            "Result Outside Margin",
        ]

        ranks = rerank(nonstandard_in, scores, search_hits)
        ranks: list[ScoredResult] = [
            {"code_string": r["code_string"], "score": r["score"]} for r in ranks
        ]

        assert ranks == [
            {
                "code_string": "Influenza virus A and B and SARS-CoV-2 (COVID-19)",
                "score": pytest.approx(0.2510499656200409, abs=1e-6),
            },
            {
                "code_string": "Result outside margin that will be added back in",
                "score": 0.04,
            },
        ]
