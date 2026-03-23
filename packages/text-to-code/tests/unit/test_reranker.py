import pytest
from text_to_code.services.reranker import Reranker


class TestReranker:
    @pytest.fixture(scope="class")
    def reranker(self) -> Reranker:
        return Reranker()

    def test_reranker_empty_hits(self, reranker: Reranker) -> None:
        ranks = reranker.rerank([])
        assert len(ranks) == 0

    def test_reranker_single_search_result(self, reranker: Reranker) -> None:
        ranks = reranker.rerank(
            "Influenza virus A and B and SARS-CoV-2 (COVID-19)",
            ["Influenza virus A and B and SARS-CoV-2 (COVID-19)"],
        )
        assert ranks == [
            {"code_string": "Influenza virus A and B and SARS-CoV-2 (COVID-19)", "score": 1.0}
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
        assert ranks == []
