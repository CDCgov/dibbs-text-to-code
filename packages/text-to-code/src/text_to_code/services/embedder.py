from sentence_transformers import SentenceTransformer
from torch import Tensor

from text_to_code.models.registry import TTC_RETRIEVER

_RETRIEVER = SentenceTransformer(TTC_RETRIEVER)


class Embedder:
    """Transforms nonstandard text."""

    def embed(self, text: str) -> Tensor:
        """Encode a text string into a vector representation.

        The dimensionality and
        values of the vector form are determined by the application's default
        Retriever Model.

        :param text: Text string to embed.
        :returns: Tensor representation of input text.
        """
        return _RETRIEVER.encode(text)
