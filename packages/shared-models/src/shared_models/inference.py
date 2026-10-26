"""Wire contract between the TTC Lambda and the GPU inference service.

Both sides import these models so the request and response shapes cannot drift.
"""

from pydantic import Field

from shared_models import FrozenBaseModel

MAX_EMBED_TEXTS = 256
MAX_RANK_DOCUMENTS = 512


class EmbedRequest(FrozenBaseModel):
    """Texts to embed with the retriever model."""

    texts: list[str] = Field(min_length=1, max_length=MAX_EMBED_TEXTS)


class EmbedResponse(FrozenBaseModel):
    """One embedding per input text, in input order."""

    embeddings: list[list[float]]
    model_id: str


class RankRequest(FrozenBaseModel):
    """A query and the candidate documents to score with the reranker model."""

    query: str
    documents: list[str] = Field(max_length=MAX_RANK_DOCUMENTS)


class RankItem(FrozenBaseModel):
    """The reranker score for one document, identified by its index in the request."""

    corpus_id: int
    score: float


class RankResponse(FrozenBaseModel):
    """Reranker scores sorted from highest to lowest."""

    results: list[RankItem]
    model_id: str


class ServedModelInfo(FrozenBaseModel):
    """A model loaded by the inference service."""

    uri: str
    """Where the service loaded the model from (S3 prefix, local path, or Hugging Face repo id)."""
    device: str
    dtype: str


class InfoResponse(FrozenBaseModel):
    """The models and runtime the inference service is serving with."""

    retriever: ServedModelInfo
    reranker: ServedModelInfo
    embedding_dimension: int
    torch_version: str
    cuda_version: str | None = None
    gpu_name: str | None = None
