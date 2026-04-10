import pytest

from text_to_code.services.reranker import Reranker


class TestReranker:
    """Test the reranker.

    TODO: The tests in this class are comparing floating points and therefore we should not be checking for equality.
    """

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
            {"code_string": "Influenza virus A and B and SARS-CoV-2 (COVID-19)", "score": 0.99}
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
