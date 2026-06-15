import logging

from sentence_transformers import SentenceTransformer
from torch import Tensor

from text_to_code.models.registry import TTC_RETRIEVER
from text_to_code.services.utils import get_model_info

logger = logging.getLogger(__name__)

_RETRIEVER = SentenceTransformer(TTC_RETRIEVER)
RETRIEVER_MODEL_INFO = get_model_info(TTC_RETRIEVER)


def embed(text: str) -> Tensor:
    """Encode a text string into a vector representation.

    The dimensionality and values of the vector form are determined
    by the application's default Retriever Model.

    :param text: Text string to embed.
    :returns: Tensor representation of input text.
    """
    logger.info(
        "Embedding the text string.",
        extra={"status": "processing"},
    )
    return _RETRIEVER.encode(text)
