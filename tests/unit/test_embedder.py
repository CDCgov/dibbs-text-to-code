import pytest

from dibbs_text_to_code.services.embedder import Embedder


class TestEmbedder:
    @pytest.fixture(scope="class")
    def embedder(self) -> Embedder:
        return Embedder()

    @pytest.mark.parametrize(
        ("input_text"), ["Influenza virus A and B and SARS-CoV-2 (COVID-19)", "COVID"]
    )
    def test_embed(self, embedder: Embedder, input_text: str) -> None:
        embedding = embedder.embed(input_text)

        expected_embedding_length = 768

        assert len(embedding) == expected_embedding_length
        # this is only for the small model - 384
        # this is only for the Qwen model - 4096  # number of dimensions
        assert len(embedding.shape) == 1  # Assuming a 1D tensor for a single string
