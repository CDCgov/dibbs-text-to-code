from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ModelInfo(BaseModel):
    """Info about a Text-to-Code model sourced from Hugging Face."""

    model_config = ConfigDict(frozen=True)

    id: str | None
    author: str | None
    created_at: datetime | None
    last_modified: datetime | None


class TTCModelInfo(BaseModel):
    """Info about the Text-to-Code models used in a TTC run."""

    model_config = ConfigDict(frozen=True)

    retriever: ModelInfo
    reranker: ModelInfo
