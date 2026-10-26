import logging
import os
import threading
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager

import numpy as np
from fastapi import FastAPI, HTTPException, status

from inference_service.models import LoadedModels, load_models
from inference_service.settings import Settings
from shared_models.inference import (
    EmbedRequest,
    EmbedResponse,
    InfoResponse,
    RankItem,
    RankRequest,
    RankResponse,
)

logger = logging.getLogger(__name__)


def _exit_process() -> None:
    # Exit hard so ECS replaces the task; a server that can never load its models
    # should not sit there failing health checks until the start period runs out.
    os._exit(1)


def create_app(
    loader: Callable[[Settings], LoadedModels] = load_models,
    settings_factory: Callable[[], Settings] = Settings.from_env,
    on_load_failure: Callable[[], None] = _exit_process,
) -> FastAPI:
    """Creates the inference service app.

    Models load in a background thread so the port binds immediately and ``/health``
    can report progress while large weights download.

    Args:
        loader: Loads the models from settings.
        settings_factory: Builds the settings, called in the loader thread.
        on_load_failure: Called if loading raises.

    Returns:
        The FastAPI app.
    """
    models: list[LoadedModels] = []

    def load() -> None:
        try:
            models.append(loader(settings_factory()))
        except Exception:
            logger.exception("Failed to load models")
            on_load_failure()

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        threading.Thread(target=load, name="model-loader", daemon=True).start()
        yield

    def loaded() -> LoadedModels:
        if not models:
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Models are still loading")
        return models[0]

    app = FastAPI(title="TTC inference service", lifespan=lifespan)

    @app.get("/health")
    def health() -> dict[str, str]:
        loaded()
        return {"status": "ok"}

    @app.get("/info")
    def info() -> InfoResponse:
        return loaded().info

    @app.post("/embed")
    def embed(request: EmbedRequest) -> EmbedResponse:
        served = loaded()
        with served.lock:
            embeddings = np.asarray(served.retriever.encode(request.texts), dtype=np.float32)
        return EmbedResponse(embeddings=embeddings.tolist(), model_id=served.info.retriever.uri)

    @app.post("/rank")
    def rank(request: RankRequest) -> RankResponse:
        served = loaded()
        results: list[RankItem] = []
        if request.documents:
            with served.lock:
                ranks = served.reranker.rank(request.query, request.documents)
            results = [
                RankItem(corpus_id=int(r["corpus_id"]), score=float(r["score"])) for r in ranks
            ]
        return RankResponse(results=results, model_id=served.info.reranker.uri)

    return app


app = create_app()
