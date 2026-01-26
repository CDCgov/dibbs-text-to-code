from sentence_transformers import SentenceTransformer
from torch import Tensor

from dibbs_text_to_code.configs.general import _model_name as default_model_name


class Embedder:
    """Transforms nonstandard text."""

    _model: SentenceTransformer | None = None

    def __init__(self, model_name: str = default_model_name):
        """Initialize evaluator.

        :model_name: Model name string.
        """
        self._model_name = model_name

    def embed(self, input_text: str) -> Tensor:
        """Take a text string and embeds it as a vector using a model as defined in config.py.

        :param input_text: Text string to embed.
        :returns: Tensor representation of input text.
        """
        if self._model is None:
            self._model = SentenceTransformer(self._model_name)
        return self._model.encode(input_text)
