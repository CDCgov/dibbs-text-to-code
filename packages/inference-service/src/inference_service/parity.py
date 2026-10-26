"""Compare the served models' outputs on CPU and on the GPU.

Run inside the inference container (``aws ecs execute-command``) with the same model
URIs the service uses::

    python -m inference_service.parity --cases s3://<bucket>/parity/test_cases.json

The cases file uses the ``scripts/test_cases.json`` format. Exits non-zero when the
two devices disagree by more than the tolerances.
"""

import argparse
import json
import logging
import sys
from dataclasses import replace
from pathlib import Path
from urllib.parse import urlparse

import boto3
import numpy as np

from inference_service.models import LoadedModels, load_models
from inference_service.settings import Settings

logger = logging.getLogger(__name__)

DOCUMENTS_PER_QUERY = 10


def _read_cases(location: str) -> list[dict[str, str]]:
    if location.startswith("s3://"):
        parsed = urlparse(location)
        body = boto3.client("s3").get_object(Bucket=parsed.netloc, Key=parsed.path.lstrip("/"))
        data = json.loads(body["Body"].read())
    else:
        data = json.loads(Path(location).read_text())
    return data["test_cases"]


def compare(cpu: LoadedModels, gpu: LoadedModels, cases: list[dict[str, str]]) -> dict[str, float]:
    """Runs the cases through both sets of models and measures how far apart they are.

    Each query is ranked against its correct LOINC name plus the names from the following
    cases, so every rank call has the same number of plausible-looking documents.

    Args:
        cpu: Models loaded on the CPU.
        gpu: Models loaded on the GPU.
        cases: Test cases with ``nonstandard_in`` and ``correct_standardized_code`` keys.

    Returns:
        The largest embedding cosine distance, the share of queries with the same top
        reranked document, and the largest reranker score difference.
    """
    queries = [c["nonstandard_in"] for c in cases]
    names = [c["correct_standardized_code"] for c in cases]

    cpu_embeddings = cpu.retriever.encode(queries)
    gpu_embeddings = gpu.retriever.encode(queries)
    cosine = np.sum(cpu_embeddings * gpu_embeddings, axis=1) / (
        np.linalg.norm(cpu_embeddings, axis=1) * np.linalg.norm(gpu_embeddings, axis=1)
    )

    agreements = 0
    max_score_delta = 0.0
    for i, query in enumerate(queries):
        documents = [names[(i + j) % len(names)] for j in range(DOCUMENTS_PER_QUERY)]
        cpu_ranks = cpu.reranker.rank(query, documents)
        gpu_ranks = gpu.reranker.rank(query, documents)
        agreements += cpu_ranks[0]["corpus_id"] == gpu_ranks[0]["corpus_id"]
        cpu_scores = {r["corpus_id"]: float(r["score"]) for r in cpu_ranks}
        for r in gpu_ranks:
            max_score_delta = max(max_score_delta, abs(cpu_scores[r["corpus_id"]] - r["score"]))

    return {
        "max_embedding_cosine_distance": float(np.max(1 - cosine)),
        "rerank_top1_agreement": agreements / len(queries),
        "max_rerank_score_delta": max_score_delta,
    }


def main() -> None:
    """Loads the models on both devices, compares them, and prints the results as JSON."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", required=True, help="Local path or s3:// URI of test cases")
    parser.add_argument("--max-cosine-distance", type=float, default=1e-6)
    parser.add_argument("--min-top1-agreement", type=float, default=1.0)
    args = parser.parse_args()
    logging.basicConfig(level="INFO")

    settings = Settings.from_env()
    gpu = load_models(settings)
    cpu = load_models(replace(settings, model_device="cpu"))
    results = compare(cpu, gpu, _read_cases(args.cases))
    print(json.dumps(results, indent=2))  # noqa: T201

    if (
        results["max_embedding_cosine_distance"] > args.max_cosine_distance
        or results["rerank_top1_agreement"] < args.min_top1_agreement
    ):
        sys.exit(1)


if __name__ == "__main__":
    main()
