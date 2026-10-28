import time
from http import HTTPStatus
from typing import Any

import numpy as np
import pytest
from fastapi.testclient import TestClient

from inference_service.app import create_app
from inference_service.models import LoadedModels
from inference_service.settings import Settings
from shared_models.inference import (
    MAX_EMBED_TEXTS,
    InfoResponse,
    RankResponse,
    ServedModelInfo,
)

EMBEDDING_DIMENSION = 3
SETTINGS = Settings(retriever_model_uri="s3://b/retriever/", reranker_model_uri="s3://b/reranker/")


class FakeRetriever:
    def encode(self, sentences: list[str]) -> np.ndarray:
        return np.array([[float(len(s)), 1.0, 0.5] for s in sentences], dtype=np.float32)


class FakeReranker:
    def rank(self, query: str, documents: list[str]) -> list[dict[str, Any]]:
        scores = [np.float32(len(d) / 100) for d in documents]
        order = sorted(range(len(documents)), key=lambda i: scores[i], reverse=True)
        return [{"corpus_id": i, "score": scores[i]} for i in order]


def fake_models(settings: Settings) -> LoadedModels:
    served = ServedModelInfo(uri=settings.retriever_model_uri, device="cpu", dtype="float32")
    return LoadedModels(
        retriever=FakeRetriever(),
        reranker=FakeReranker(),
        info=InfoResponse(
            retriever=served,
            reranker=served.model_copy(update={"uri": settings.reranker_model_uri}),
            embedding_dimension=EMBEDDING_DIMENSION,
            torch_version="test",
        ),
    )


def wait_until_healthy(client: TestClient) -> None:
    deadline = time.monotonic() + 5
    while client.get("/health").status_code != HTTPStatus.OK:
        assert time.monotonic() < deadline, "service never became healthy"
        time.sleep(0.01)


@pytest.fixture
def client():
    app = create_app(loader=fake_models, settings_factory=lambda: SETTINGS)
    with TestClient(app) as client:
        wait_until_healthy(client)
        yield client


def test_health_is_unavailable_while_loading():
    def never_loads(_: Settings) -> LoadedModels:
        time.sleep(1)
        raise AssertionError("not reached in this test")

    app = create_app(
        loader=never_loads, settings_factory=lambda: SETTINGS, on_load_failure=lambda: None
    )
    with TestClient(app) as client:
        assert client.get("/health").status_code == HTTPStatus.SERVICE_UNAVAILABLE
        assert (
            client.post("/embed", json={"texts": ["a"]}).status_code
            == HTTPStatus.SERVICE_UNAVAILABLE
        )


def test_load_failure_calls_handler():
    failures = []

    def broken(_: Settings) -> LoadedModels:
        raise RuntimeError("no CUDA")

    app = create_app(
        loader=broken, settings_factory=lambda: SETTINGS, on_load_failure=lambda: failures.append(1)
    )
    with TestClient(app):
        deadline = time.monotonic() + 5
        while not failures:
            assert time.monotonic() < deadline
            time.sleep(0.01)
    assert failures == [1]


def test_embed_returns_one_row_per_text_in_order(client):
    response = client.post("/embed", json={"texts": ["abc", "a", "abcdef"]})

    assert response.status_code == HTTPStatus.OK
    body = response.json()
    assert body["model_id"] == "s3://b/retriever/"
    assert [row[0] for row in body["embeddings"]] == [3.0, 1.0, 6.0]
    assert all(len(row) == EMBEDDING_DIMENSION for row in body["embeddings"])


@pytest.mark.parametrize("texts", [[], ["x"] * (MAX_EMBED_TEXTS + 1)])
def test_embed_rejects_empty_or_oversized_batches(client, texts):
    assert (
        client.post("/embed", json={"texts": texts}).status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    )


def test_rank_sorts_descending_and_keeps_corpus_ids(client):
    response = client.post("/rank", json={"query": "q", "documents": ["aa", "aaaa", "a"]})

    assert response.status_code == HTTPStatus.OK
    body = RankResponse.model_validate(response.json())
    assert [r.corpus_id for r in body.results] == [1, 0, 2]
    assert [r.score for r in body.results] == pytest.approx([0.04, 0.02, 0.01])
    assert body.model_id == "s3://b/reranker/"


def test_rank_with_no_documents_skips_the_model(client):
    response = client.post("/rank", json={"query": "q", "documents": []})

    assert response.status_code == HTTPStatus.OK
    assert response.json()["results"] == []


def test_info_describes_served_models(client):
    info = InfoResponse.model_validate(client.get("/info").json())

    assert info.retriever.uri == "s3://b/retriever/"
    assert info.reranker.uri == "s3://b/reranker/"
    assert info.embedding_dimension == EMBEDDING_DIMENSION
