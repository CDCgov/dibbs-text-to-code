from sentence_transformers import SentenceTransformer
from torch import Tensor

from text_to_code.models.registry import default_model

_MODEL = SentenceTransformer(default_model)


class Embedder:
    """Transforms nonstandard text."""

    def embed(self, text: str) -> Tensor:
        """Take a text string and embeds it as a vector using a model as defined in config.py.

        :param text: Text string to embed.
        :returns: Tensor representation of input text.
        """
        return _MODEL.encode(text)
