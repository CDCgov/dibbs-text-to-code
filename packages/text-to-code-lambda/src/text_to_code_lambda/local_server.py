r"""Local FastAPI dev server for the text-to-code demo API.

Runs the same ``service`` logic as the Lambda Function URL handler, but as a
plain HTTP server so the demo can be developed locally against the real AWS
OpenSearch domain ("local backend -> AWS data"). It is not deployed;
``fastapi``/``uvicorn`` live in the package's ``dev`` dependency group.

Run (from the repo root)::

    OPENSEARCH_ENDPOINT_URL=https://<domain-endpoint> \\
    OPENSEARCH_INDEX=ttc-index \\
    AWS_REGION=us-east-2 \\
    uv run --group dev uvicorn text_to_code_lambda.local_server:app --port 8080

This requires AWS credentials that are permitted on the OpenSearch domain and
local access to the retriever/reranker models (cached or via ``HF_TOKEN``).
"""

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

import lambda_handler

from . import service

app = FastAPI(title="Text-to-Code demo API")

# For local dev, allow all origins by default. Set CORS_ALLOW_ORIGINS to a
# comma-separated list to restrict to a specific page origin.
_origins = os.getenv("CORS_ALLOW_ORIGINS", "*")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if _origins == "*" else [o.strip() for o in _origins.split(",")],
    allow_methods=["*"],
    allow_headers=["*"],
)


class TextToCodeRequest(BaseModel):
    """Request body for ``POST /text-to-code``."""

    inputs: list[str]
    data_field: str | None = None


@app.post("/text-to-code")
def text_to_code(request: TextToCodeRequest) -> dict:
    """Map lab text strings to LOINC codes.

    :param request: The inputs to standardize and an optional data field.
    :return: ``{"results": [...]}`` with one row per input.
    """
    data_field = service.parse_data_field(request.data_field)
    opensearch_client = lambda_handler.create_opensearch_client()
    results = service.results_for_inputs(request.inputs, data_field, opensearch_client)
    return {"results": results}


@app.get("/health")
def health() -> dict:
    """Liveness check that does not touch OpenSearch."""
    return {"status": "ok"}
