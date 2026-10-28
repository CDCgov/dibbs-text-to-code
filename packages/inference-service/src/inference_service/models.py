import logging
import threading
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol

import torch
from sentence_transformers import CrossEncoder, SentenceTransformer

from inference_service.model_store import resolve_model
from inference_service.settings import Settings
from shared_models.inference import InfoResponse, ServedModelInfo

logger = logging.getLogger(__name__)

_WARMUP_TEXT = "Influenza virus A and B and SARS-CoV-2 (COVID-19)"


class Encoder(Protocol):
    """The subset of ``SentenceTransformer`` the service uses."""

    def encode(self, sentences: list[str], /) -> Any:  # noqa: ANN401 - torch, numpy, or list
        """Embeds a batch of texts."""
        ...


class Ranker(Protocol):
    """The subset of ``CrossEncoder`` the service uses."""

    def rank(self, query: str, documents: list[str], /) -> Sequence[Mapping[Any, Any]]:
        """Scores documents against a query, highest score first."""
        ...


@dataclass
class LoadedModels:
    """The models the service is serving, plus a lock that serializes GPU calls."""

    retriever: Encoder
    reranker: Ranker
    info: InfoResponse
    lock: threading.Lock = field(default_factory=threading.Lock)


def load_models(settings: Settings) -> LoadedModels:
    """Downloads (if needed), loads, and warms up the retriever and reranker.

    Args:
        settings: The service settings.

    Returns:
        The loaded models.

    Raises:
        RuntimeError: If CUDA was requested but is not available. Falling back to CPU
            would hide a driver or image problem behind very slow responses.
    """
    if settings.model_device == "cuda" and not torch.cuda.is_available():
        raise RuntimeError(
            f"MODEL_DEVICE=cuda but CUDA is not available (torch {torch.__version__}, "
            f"built for CUDA {torch.version.cuda})"
        )
    # Keep float32 matmuls in full precision so GPU embeddings stay as close as possible to
    # the CPU-embedded queries and corpus.
    torch.set_float32_matmul_precision("highest")

    model_kwargs: dict[str, Any] | None = None
    if settings.model_dtype != "float32":
        model_kwargs = {"dtype": getattr(torch, settings.model_dtype)}

    start = time.monotonic()
    retriever_path = resolve_model(settings.retriever_model_uri, settings.model_cache_dir)
    reranker_path = resolve_model(settings.reranker_model_uri, settings.model_cache_dir)
    logger.info("Resolved models in %.1fs", time.monotonic() - start)

    start = time.monotonic()
    retriever = SentenceTransformer(
        str(retriever_path), device=settings.model_device, model_kwargs=model_kwargs
    )
    reranker = CrossEncoder(
        str(reranker_path), device=settings.model_device, model_kwargs=model_kwargs
    )
    retriever.encode([_WARMUP_TEXT])
    reranker.rank(_WARMUP_TEXT, [_WARMUP_TEXT])
    logger.info("Loaded and warmed up models in %.1fs", time.monotonic() - start)

    gpu_name = torch.cuda.get_device_name(0) if settings.model_device == "cuda" else None
    info = InfoResponse(
        retriever=ServedModelInfo(
            uri=settings.retriever_model_uri,
            device=settings.model_device,
            dtype=settings.model_dtype,
        ),
        reranker=ServedModelInfo(
            uri=settings.reranker_model_uri,
            device=settings.model_device,
            dtype=settings.model_dtype,
        ),
        embedding_dimension=retriever.get_embedding_dimension() or 0,
        torch_version=torch.__version__,
        cuda_version=torch.version.cuda,
        gpu_name=gpu_name,
    )
    logger.info("Serving %s", info.model_dump_json())
    return LoadedModels(retriever=retriever, reranker=reranker, info=info)
