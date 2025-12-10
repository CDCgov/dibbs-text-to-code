from sentence_transformers import SentenceTransformer
from torch import Tensor

from dibbs_text_to_code.configs import MODEL_NAME

model = SentenceTransformer(MODEL_NAME)


def embed(input_text: str) -> Tensor:
    """Embed text."""
    return model.encode(input_text)
