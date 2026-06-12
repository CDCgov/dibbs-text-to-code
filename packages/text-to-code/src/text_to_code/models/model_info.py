from datetime import datetime

from pydantic import FrozenModel


class ModelInfo(FrozenModel):
    """Info about a Text-to-Code model sourced from Hugging Face."""

    id: str | None
    author: str | None
    created_at: datetime | None
    last_modified: datetime | None


class TTCModelInfo(FrozenModel):
    """Info about the Text-to-Code models used in a TTC run."""

    retriever: ModelInfo
    reranker: ModelInfo
