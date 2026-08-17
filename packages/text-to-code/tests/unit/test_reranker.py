from text_to_code.models.registry import HIGH_SCORE, LOW_SCORE, MAX_MARGIN
from text_to_code.services.reranker import (
    ScoredResult,
    rerank,
)


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
        scores = [HIGH_SCORE] * len(search_hits)
        ranks = rerank(nonstandard_in, scores, search_hits)
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

    def test_reranker_prunes_hits_outside_margin(self) -> None:
        nonstandard_in = "Influenza virus A and B and SARS-CoV-2 (COVID-19)"
        scores = [
            LOW_SCORE,
            LOW_SCORE - (MAX_MARGIN * 2),
        ]
        search_hits = [
            "Influenza virus A and B and SARS-CoV-2 (COVID-19)",
            "Result Outside Margin",
        ]

        ranks = rerank(nonstandard_in, scores, search_hits)
        ranks: list[ScoredResult] = [
            {"code_string": r["code_string"], "score": round(float(r["score"]), 3)} for r in ranks
        ]

        assert ranks == [
            {"code_string": "Influenza virus A and B and SARS-CoV-2 (COVID-19)", "score": 0.99}
        ]
