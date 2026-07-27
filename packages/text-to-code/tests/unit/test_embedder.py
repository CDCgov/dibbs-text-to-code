import pytest

from text_to_code.services.embedder import embed, embed_batch


class TestEmbedder:
    @pytest.mark.parametrize(
        ("input_text"), ["Influenza virus A and B and SARS-CoV-2 (COVID-19)", "COVID"]
    )
    def test_embed(self, input_text: str) -> None:
        embedding = embed(input_text)

        expected_embedding_length = 1024

        assert len(embedding) == expected_embedding_length
        assert len(embedding.shape) == 1  # Assuming a 1D tensor for a single string

    def test_embed_batch(self) -> None:
        embeddings = embed_batch(["Influenza virus A and B and SARS-CoV-2 (COVID-19)", "COVID"])

        expected_embedding_count = 2
        expected_embedding_length = 1024

        assert len(embeddings) == expected_embedding_count
        assert embeddings.shape == (
            expected_embedding_count,
            expected_embedding_length,
        )
