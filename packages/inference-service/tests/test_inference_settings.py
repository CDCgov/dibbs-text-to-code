from pathlib import Path

import pytest

from inference_service.settings import Settings


def test_from_env(monkeypatch):
    monkeypatch.setenv("RETRIEVER_MODEL_URI", "s3://b/retriever/")
    monkeypatch.setenv("RERANKER_MODEL_URI", "s3://b/reranker/")
    monkeypatch.setenv("MODEL_DTYPE", "bfloat16")
    monkeypatch.setenv("MODEL_DEVICE", "cpu")
    monkeypatch.setenv("MODEL_CACHE_DIR", "/tmp/models")  # noqa: S108

    settings = Settings.from_env()

    assert settings == Settings(
        retriever_model_uri="s3://b/retriever/",
        reranker_model_uri="s3://b/reranker/",
        model_dtype="bfloat16",
        model_device="cpu",
        model_cache_dir=Path("/tmp/models"),  # noqa: S108
    )


def test_from_env_defaults(monkeypatch):
    monkeypatch.setenv("RETRIEVER_MODEL_URI", "r")
    monkeypatch.setenv("RERANKER_MODEL_URI", "x")
    for name in ("MODEL_DTYPE", "MODEL_DEVICE", "MODEL_CACHE_DIR"):
        monkeypatch.delenv(name, raising=False)

    settings = Settings.from_env()

    assert settings.model_dtype == "float32"
    assert settings.model_device == "cuda"
    assert settings.model_cache_dir == Path("/models")


def test_from_env_requires_both_models(monkeypatch):
    monkeypatch.setenv("RETRIEVER_MODEL_URI", "r")
    monkeypatch.delenv("RERANKER_MODEL_URI", raising=False)

    with pytest.raises(ValueError, match="RERANKER_MODEL_URI"):
        Settings.from_env()


def test_rejects_unknown_dtype():
    with pytest.raises(ValueError, match="MODEL_DTYPE"):
        Settings(retriever_model_uri="r", reranker_model_uri="x", model_dtype="int8")
