import pytest

from text_to_code.services.reranker import Reranker


class TestReranker:
    @pytest.fixture(scope="class")
    def reranker(self) -> Reranker:
        return Reranker()

    def test_reranker_empty_hits(self, reranker: Reranker) -> None:
        ranks = reranker.rerank("Influenza virus A and B and SARS-CoV-2 (COVID-19)", [])
        assert len(ranks) == 0

    def test_reranker_single_search_result(self, reranker: Reranker) -> None:
        ranks = reranker.rerank(
            "Influenza virus A and B and SARS-CoV-2 (COVID-19)",
            ["Influenza virus A and B and SARS-CoV-2 (COVID-19)"],
        )
        ranks = [
            {"code_string": r["code_string"], "score": round(float(r["score"]), 3)} for r in ranks
        ]
        assert ranks == [
            {"code_string": "Influenza virus A and B and SARS-CoV-2 (COVID-19)", "score": 0.973}
        ]

    def test_reranker_multiple_hits(self, reranker: Reranker) -> None:
        nonstandard_in = "albumin/creatinine ratio (acr)"
        search_hits = [
            "Albumin/Creatinine [Ratio] in Urine",
            "Albumin/Creatinine (U) [Mass ratio]",
            "Albumin/Creatinine [Ratio] in 24 hour Urine",
            "Albumin/Creatinine (U) [Molar ratio]",
        ]
        ranks = reranker.rerank(nonstandard_in, search_hits)
        ranks = [
            {"code_string": r["code_string"], "score": round(float(r["score"]), 3)} for r in ranks
        ]
        assert ranks == [
            {
                "code_string": "Albumin/Creatinine (U) [Mass ratio]",
                "score": 0.755,
            },
            {
                "code_string": "Albumin/Creatinine (U) [Molar ratio]",
                "score": 0.73,
            },
            {
                "code_string": "Albumin/Creatinine [Ratio] in 24 hour Urine",
                "score": 0.701,
            },
            {"code_string": "Albumin/Creatinine [Ratio] in Urine", "score": 0.672},
        ]
