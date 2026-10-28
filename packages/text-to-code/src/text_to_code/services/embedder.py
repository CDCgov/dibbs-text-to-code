import logging

import numpy as np
from sentence_transformers import SentenceTransformer

from text_to_code.models.registry import TTC_RETRIEVER
from text_to_code.services.inference_client import RemoteSentenceTransformer, get_inference_client
from text_to_code.services.utils import get_model_info

logger = logging.getLogger(__name__)


def _load_retriever() -> SentenceTransformer | RemoteSentenceTransformer:
    """Returns the inference service client if configured, else the in-process model."""
    client = get_inference_client()
    if client is not None:
        return RemoteSentenceTransformer(client)
    return SentenceTransformer(TTC_RETRIEVER)


_RETRIEVER = _load_retriever()
RETRIEVER_MODEL_INFO = get_model_info(TTC_RETRIEVER)


def embed(text: str) -> np.ndarray:
    """Encode a text string into a vector representation.

    The dimensionality and values of the vector form are determined
    by the application's default Retriever Model.

    :param text: Text string to embed.
    :returns: Array representation of input text.
    """
    logger.info(
        "Embedding the text string.",
        extra={"status": "processing"},
    )
    return _RETRIEVER.encode(text)


def embed_batch(texts: list[str]) -> np.ndarray:
    """Encode a batch of text strings into vector representations.

    A single batched forward pass amortizes far better than repeated
    single-string calls, so callers with several texts should prefer this
    over calling :func:`embed` in a loop.

    :param texts: Text strings to embed.
    :returns: Array of one embedding row per input text, in input order.
    """
    logger.info(
        "Embedding a batch of text strings.",
        extra={"status": "processing", "batch_size": len(texts)},
    )
    return _RETRIEVER.encode(texts)
