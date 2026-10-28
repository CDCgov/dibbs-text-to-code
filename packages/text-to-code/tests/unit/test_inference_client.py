import logging
from dataclasses import dataclass, field
from http import HTTPStatus
from typing import Any

import numpy as np
import pytest
import requests

from shared_models.inference import MAX_EMBED_TEXTS
from text_to_code.services import embedder, inference_client, reranker
from text_to_code.services.inference_client import (
    InferenceClient,
    InferenceServiceUnavailableError,
    RemoteCrossEncoder,
    RemoteSentenceTransformer,
    get_inference_client,
)

READY_TIMEOUT_S = 30.0


@dataclass
class FakeResponse:
    status_code: int
    body: dict | None = None

    def json(self) -> dict | None:
        return self.body

    def raise_for_status(self) -> None:
        if self.status_code >= HTTPStatus.BAD_REQUEST:
            raise requests.HTTPError(f"HTTP {self.status_code}")


class FakeSession:
    """Returns (or raises) queued outcomes in order and records each request."""

    def __init__(self, *outcomes: FakeResponse | Exception):
        """Queue the outcomes."""
        self.outcomes = list(outcomes)
        self.requests: list[tuple[str, str, dict | None]] = []

    def request(self, method: str, url: str, **kwargs: Any) -> FakeResponse:
        self.requests.append((method, url, kwargs.get("json")))
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


@dataclass
class FakeClock:
    now: float = 0.0
    sleeps: list[float] = field(default_factory=list)

    def __call__(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


def make_client(session: FakeSession, clock: FakeClock | None = None) -> InferenceClient:
    clock = clock or FakeClock()
    return InferenceClient(
        "http://inference.test:8080/",
        ready_timeout_s=READY_TIMEOUT_S,
        session=session,  # ty: ignore[invalid-argument-type]
        clock=clock,
        sleep=clock.sleep,
    )


def embed_response(rows: list[list[float]]) -> FakeResponse:
    return FakeResponse(HTTPStatus.OK, {"embeddings": rows, "model_id": "s3://b/r/"})


class TestInferenceClient:
    def test_embed_returns_float32_rows(self):
        session = FakeSession(embed_response([[0.1, 0.2], [0.3, 0.4]]))

        embeddings = make_client(session).embed(["a", "b"])

        assert embeddings.dtype == np.float32
        assert embeddings.shape == (2, 2)
        assert session.requests == [
            ("POST", "http://inference.test:8080/embed", {"texts": ["a", "b"]})
        ]

    def test_embed_splits_large_batches(self):
        texts = [str(i) for i in range(MAX_EMBED_TEXTS + 1)]
        session = FakeSession(embed_response([[0.0]] * MAX_EMBED_TEXTS), embed_response([[1.0]]))

        embeddings = make_client(session).embed(texts)

        assert embeddings.shape == (MAX_EMBED_TEXTS + 1, 1)
        assert [len((body or {})["texts"]) for _, _, body in session.requests] == [
            MAX_EMBED_TEXTS,
            1,
        ]

    def test_rank_returns_cross_encoder_shape(self):
        session = FakeSession(
            FakeResponse(
                HTTPStatus.OK,
                {
                    "results": [{"corpus_id": 1, "score": 0.9}, {"corpus_id": 0, "score": 0.1}],
                    "model_id": "s3://b/x/",
                },
            )
        )

        ranks = make_client(session).rank("q", ["a", "b"])

        assert ranks == [{"corpus_id": 1, "score": 0.9}, {"corpus_id": 0, "score": 0.1}]

    def test_rank_without_documents_skips_the_service(self):
        session = FakeSession()

        assert make_client(session).rank("q", []) == []
        assert session.requests == []

    @pytest.mark.parametrize(
        "cold",
        [
            requests.ConnectionError("Name or service not known"),
            requests.Timeout(),
            FakeResponse(HTTPStatus.SERVICE_UNAVAILABLE),
            FakeResponse(HTTPStatus.BAD_GATEWAY),
        ],
    )
    def test_waits_for_a_cold_service(self, cold, caplog):
        clock = FakeClock()
        session = FakeSession(cold, cold, embed_response([[1.0]]))

        with caplog.at_level(logging.WARNING, logger=inference_client.__name__):
            embeddings = make_client(session, clock).embed(["a"])

        assert embeddings.tolist() == [[1.0]]
        assert clock.sleeps == [1.0, 2.0]
        # One line when the wait starts and one when it ends, not one per retry.
        assert [r.getMessage().split(":")[0] for r in caplog.records] == [
            "waiting_for_inference_service",
            "inference_service_ready",
        ]

    def test_gives_up_at_the_deadline(self):
        clock = FakeClock()
        session = FakeSession(*[requests.ConnectionError()] * 100)

        with pytest.raises(InferenceServiceUnavailableError, match="not ready after 30s"):
            make_client(session, clock).embed(["a"])

        assert clock.now == pytest.approx(READY_TIMEOUT_S)
        assert max(clock.sleeps) <= 10.0  # noqa: PLR2004 - default max poll interval

    def test_client_errors_are_not_retried(self):
        session = FakeSession(FakeResponse(HTTPStatus.UNPROCESSABLE_ENTITY))

        with pytest.raises(requests.HTTPError):
            make_client(session).embed(["a"])

        assert len(session.requests) == 1


class TestRemoteAdapters:
    def test_encode_matches_sentence_transformer_shapes(self):
        session = FakeSession(embed_response([[1.0, 2.0]]), embed_response([[1.0, 2.0]]))
        retriever = RemoteSentenceTransformer(make_client(session))

        assert retriever.encode("a").shape == (2,)
        assert retriever.encode(["a"]).shape == (1, 2)

    def test_rank_delegates(self, mocker):
        client = mocker.Mock(spec=InferenceClient)
        client.rank.return_value = [{"corpus_id": 0, "score": 0.5}]

        assert RemoteCrossEncoder(client).rank("q", ["a"]) == [{"corpus_id": 0, "score": 0.5}]
        client.rank.assert_called_once_with("q", ["a"])


class TestModelSelection:
    @pytest.fixture
    def service_url(self, monkeypatch):
        get_inference_client.cache_clear()
        monkeypatch.setattr(inference_client, "INFERENCE_SERVICE_URL", "http://inference.test:8080")
        yield
        get_inference_client.cache_clear()

    def test_no_client_without_url(self, monkeypatch):
        get_inference_client.cache_clear()
        monkeypatch.setattr(inference_client, "INFERENCE_SERVICE_URL", None)

        assert get_inference_client() is None
        get_inference_client.cache_clear()

    @pytest.mark.usefixtures("service_url")
    def test_remote_models_when_url_is_set(self):
        assert isinstance(embedder._load_retriever(), RemoteSentenceTransformer)
        assert isinstance(reranker._load_reranker(), RemoteCrossEncoder)
