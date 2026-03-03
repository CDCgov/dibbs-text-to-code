import pytest
from text_to_code.services.embedder import embed


class TestEmbedder:
    @pytest.mark.parametrize(
        ("input_text"), ["Influenza virus A and B and SARS-CoV-2 (COVID-19)", "COVID"]
    )
    def test_embed(self, input_text: str) -> None:
        embedding = embed(input_text)

        expected_embedding_length = 1024

        assert len(embedding) == expected_embedding_length
        assert len(embedding.shape) == 1  # Assuming a 1D tensor for a single string
