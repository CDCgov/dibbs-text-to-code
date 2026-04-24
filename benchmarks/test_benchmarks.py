from text_to_code.services.reranker import rerank


def test_reranker_multiple_hits(benchmark) -> None:
    nonstandard_in = "albumin/creatinine ratio (acr)"
    search_hits = [
        "Albumin/Creatinine [Ratio] in Urine",
        "Albumin/Creatinine (U) [Mass ratio]",
        "Albumin/Creatinine [Ratio] in 24 hour Urine",
        "Albumin/Creatinine (U) [Molar ratio]",
    ]
    benchmark(rerank, nonstandard_in, search_hits)
