import pytest

from text_to_code.services.reranker import rerank


class TestReranker:
    def test_reranker_empty_hits(self) -> None:
        ranks = rerank("Influenza virus A and B and SARS-CoV-2 (COVID-19)", [])
        assert len(ranks) == 0

    def test_reranker_single_search_result(self) -> None:
        ranks = rerank(
            "Influenza virus A and B and SARS-CoV-2 (COVID-19)",
            ["Influenza virus A and B and SARS-CoV-2 (COVID-19)"],
        )
        assert ranks[0].code_string == "Influenza virus A and B and SARS-CoV-2 (COVID-19)"
        assert ranks[0].score == pytest.approx(0.989, abs=0.01)

    def test_reranker_multiple_hits(self) -> None:
        nonstandard_in = "albumin/creatinine ratio (acr)"
        search_hits = [
            "Albumin/Creatinine [Ratio] in Urine",
            "Albumin/Creatinine (U) [Mass ratio]",
            "Albumin/Creatinine [Ratio] in 24 hour Urine",
            "Albumin/Creatinine (U) [Molar ratio]",
        ]
        ranks = rerank(nonstandard_in, search_hits)
        assert ranks[0].code_string == "Albumin/Creatinine [Ratio] in Urine"
        assert ranks[0].score == pytest.approx(0.541, abs=0.01)
        assert ranks[1].code_string == "Albumin/Creatinine [Ratio] in 24 hour Urine"
        assert ranks[1].score == pytest.approx(0.308, abs=0.01)
        assert ranks[2].code_string == "Albumin/Creatinine (U) [Mass ratio]"
        assert ranks[2].score == pytest.approx(0.21, abs=0.01)
        assert ranks[3].code_string == "Albumin/Creatinine (U) [Molar ratio]"
        assert ranks[3].score == pytest.approx(0.207, abs=0.01)
