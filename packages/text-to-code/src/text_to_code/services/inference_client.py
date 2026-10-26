"""HTTP client for the GPU inference service that serves the retriever and reranker.

When ``INFERENCE_SERVICE_URL`` is set, the embedder and reranker modules use the
adapters here instead of loading the models in-process. The service scales to zero
when idle, so the first call after a quiet period waits for it to start.
"""

import functools
import logging
import time
from collections.abc import Callable
from typing import Any

import numpy as np
import requests
from pydantic import BaseModel

from shared_models.inference import (
    MAX_EMBED_TEXTS,
    EmbedRequest,
    EmbedResponse,
    InfoResponse,
    RankRequest,
    RankResponse,
)
from text_to_code.models.registry import INFERENCE_READY_TIMEOUT_SECONDS, INFERENCE_SERVICE_URL

logger = logging.getLogger(__name__)

# Gateway errors and "still loading" both mean the service is coming up, not that the
# request is bad.
_RETRYABLE_STATUS_CODES = frozenset({502, 503, 504})


class InferenceServiceUnavailableError(RuntimeError):
    """The inference service did not become ready before the deadline."""


class InferenceClient:
    """Calls the inference service, waiting for it to come up if it is scaled to zero."""

    def __init__(  # noqa: PLR0913
        self,
        base_url: str,
        *,
        ready_timeout_s: float = 720.0,
        connect_timeout_s: float = 3.05,
        read_timeout_s: float = 60.0,
        max_poll_interval_s: float = 10.0,
        session: requests.Session | None = None,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ):
        """Initialize the client.

        Args:
            base_url: Service URL, e.g. ``http://inference.ttc.internal:8080``.
            ready_timeout_s: How long a call keeps retrying while the service is
                unreachable or still loading before giving up.
            connect_timeout_s: Per-attempt connect timeout.
            read_timeout_s: Per-attempt read timeout.
            max_poll_interval_s: Upper bound on the backoff between attempts.
            session: HTTP session, injectable for tests.
            clock: Monotonic clock, injectable for tests.
            sleep: Sleep function, injectable for tests.
        """
        self._base_url = base_url.rstrip("/")
        self._ready_timeout_s = ready_timeout_s
        self._timeout = (connect_timeout_s, read_timeout_s)
        self._max_poll_interval_s = max_poll_interval_s
        self._session = session or requests.Session()
        self._clock = clock
        self._sleep = sleep

    def embed(self, texts: list[str]) -> np.ndarray:
        """Embeds texts with the served retriever.

        Args:
            texts: Texts to embed.

        Returns:
            A float32 array with one row per text, in input order.
        """
        rows: list[list[float]] = []
        for start in range(0, len(texts), MAX_EMBED_TEXTS):
            body = EmbedRequest(texts=texts[start : start + MAX_EMBED_TEXTS])
            rows.extend(EmbedResponse.model_validate(self._post("/embed", body)).embeddings)
        return np.asarray(rows, dtype=np.float32)

    def rank(self, query: str, documents: list[str]) -> list[dict[str, Any]]:
        """Scores documents against a query with the served reranker.

        Args:
            query: The nonstandard input text.
            documents: Candidate LOINC names.

        Returns:
            ``{"corpus_id", "score"}`` dicts sorted by score, highest first, matching
            ``CrossEncoder.rank``.
        """
        if not documents:
            return []
        response = RankResponse.model_validate(
            self._post("/rank", RankRequest(query=query, documents=documents))
        )
        return [item.model_dump() for item in response.results]

    def info(self) -> InfoResponse:
        """Returns the models and runtime the service is serving with."""
        return InfoResponse.model_validate(self._request("GET", "/info"))

    def _post(self, path: str, body: BaseModel) -> Any:  # noqa: ANN401 - JSON body
        return self._request("POST", path, json=body.model_dump())

    def _request(self, method: str, path: str, **kwargs: Any) -> Any:  # noqa: ANN401 - JSON body
        url = f"{self._base_url}{path}"
        started = self._clock()
        deadline = started + self._ready_timeout_s
        delay = 1.0
        waited = False
        while True:
            try:
                response = self._session.request(method, url, timeout=self._timeout, **kwargs)
                if response.status_code not in _RETRYABLE_STATUS_CODES:
                    response.raise_for_status()
                    if waited:
                        logger.warning(
                            "inference_service_ready: inference service became ready after %.0fs",
                            self._clock() - started,
                        )
                    return response.json()
                reason = f"HTTP {response.status_code}"
            except (requests.ConnectionError, requests.Timeout) as e:
                reason = type(e).__name__

            remaining = deadline - self._clock()
            if remaining <= 0:
                raise InferenceServiceUnavailableError(
                    f"Inference service at {self._base_url} was not ready after "
                    f"{self._ready_timeout_s:.0f}s ({reason})"
                )
            # The Lambda runtime only surfaces WARNING and above from this logger, and the
            # start and end of a cold-start wait are worth seeing.
            if not waited:
                logger.warning(
                    "waiting_for_inference_service: %s from %s; waiting up to %.0fs",
                    reason,
                    self._base_url,
                    remaining,
                )
                waited = True
            self._sleep(min(delay, remaining))
            delay = min(delay * 2, self._max_poll_interval_s)


class RemoteSentenceTransformer:
    """Stands in for ``SentenceTransformer`` by calling the inference service."""

    def __init__(self, client: InferenceClient):
        """Initialize the adapter with the shared client."""
        self._client = client

    def encode(self, sentences: str | list[str]) -> np.ndarray:
        """Embeds one text (returns a 1-D array) or a list of texts (returns a 2-D array)."""
        if isinstance(sentences, str):
            return self._client.embed([sentences])[0]
        return self._client.embed(sentences)


class RemoteCrossEncoder:
    """Stands in for ``CrossEncoder`` by calling the inference service."""

    def __init__(self, client: InferenceClient):
        """Initialize the adapter with the shared client."""
        self._client = client

    def rank(self, query: str, documents: list[str]) -> list[dict[str, Any]]:
        """Scores documents against a query, highest score first."""
        return self._client.rank(query, documents)


@functools.cache
def get_inference_client() -> InferenceClient | None:
    """Returns the shared client, or ``None`` when the models run in-process."""
    if not INFERENCE_SERVICE_URL:
        return None
    return InferenceClient(INFERENCE_SERVICE_URL, ready_timeout_s=INFERENCE_READY_TIMEOUT_SECONDS)
