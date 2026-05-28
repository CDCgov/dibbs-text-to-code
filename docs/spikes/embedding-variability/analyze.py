"""Compute pairwise embedding-drift metrics and (optional) downstream KNN agreement.

Inputs:
- `outputs/vectors_<env>.json` for each env in ENVS.

Outputs:
- `outputs/metrics.json` — per-pair aggregate stats plus per-description series
  (cosine, L2, max-abs-diff).
- `outputs/knn_top1.json` — only when `--with-knn`: for each (env, description), the
  top-1 LOINC code returned by the prod KNN flow when that env's vector is the query,
  plus the 5x5 agreement matrix.
"""

from __future__ import annotations

import argparse
import itertools
import json
import os
import sys
from pathlib import Path

import numpy as np
from tqdm import tqdm

ENVS = ["azure_gpu", "azure_cpu", "mac_cpu", "mac_mps", "aws_lambda"]
OUTPUTS = Path(__file__).parent / "outputs"
PERCENTILES = [1, 5, 50, 95, 99]


def load_vectors(env: str) -> dict[str, list[float]] | None:
    path = OUTPUTS / f"vectors_{env}.json"
    if not path.exists():
        print(f"  missing: {path}", file=sys.stderr)
        return None
    return json.loads(path.read_text())


def cosine(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    num = np.sum(a * b, axis=1)
    den = np.linalg.norm(a, axis=1) * np.linalg.norm(b, axis=1)
    return num / np.where(den == 0, 1.0, den)


def summarize(values: np.ndarray) -> dict[str, float]:
    if values.size == 0:
        return {}
    summary = {
        "n": int(values.size),
        "mean": float(np.mean(values)),
        "std": float(np.std(values)),
        "min": float(np.min(values)),
        "max": float(np.max(values)),
    }
    for p in PERCENTILES:
        summary[f"p{p}"] = float(np.percentile(values, p))
    return summary


def compute_pairwise(stack: np.ndarray, descriptions: list[str], envs: list[str]) -> dict:
    pair_metrics: dict[str, dict] = {}
    env_to_idx = {e: i for i, e in enumerate(envs)}

    for a_env, b_env in itertools.combinations(envs, 2):
        a = stack[:, env_to_idx[a_env], :]
        b = stack[:, env_to_idx[b_env], :]
        cos = cosine(a, b)
        l2 = np.linalg.norm(a - b, axis=1)
        max_abs = np.max(np.abs(a - b), axis=1)

        pair_metrics[f"{a_env}__{b_env}"] = {
            "envs": [a_env, b_env],
            "cosine": summarize(cos),
            "l2": summarize(l2),
            "max_abs_diff": summarize(max_abs),
            "per_description": {
                "cosine": cos.tolist(),
                "l2": l2.tolist(),
                "max_abs_diff": max_abs.tolist(),
            },
        }
    return pair_metrics


def outlier_descriptions(
    stack: np.ndarray, descriptions: list[str], top_n: int = 10
) -> list[dict]:
    # Mean per-dimension variance across envs for each description.
    variances = np.var(stack, axis=1).mean(axis=1)  # shape (n_descs,)
    order = np.argsort(variances)[::-1][:top_n]
    return [
        {"description": descriptions[int(i)], "mean_variance_across_envs": float(variances[i])}
        for i in order
    ]


def self_pair_smoke_test(stack: np.ndarray, envs: list[str]) -> dict:
    out = {}
    for i, env in enumerate(envs):
        vec = stack[:, i, :]
        cos = cosine(vec, vec)
        out[env] = {"min": float(cos.min()), "max": float(cos.max())}
    return out


def knn_top1_per_env(
    stack: np.ndarray,
    descriptions: list[str],
    envs: list[str],
    index_name: str,
) -> dict[str, list[str | None]]:
    """For each env, query prod OpenSearch with that env's vector and capture the top-1 loinc_code."""
    from lambda_handler.lambda_handler import create_opensearch_client

    client = create_opensearch_client()
    env_to_idx = {e: i for i, e in enumerate(envs)}
    top1: dict[str, list[str | None]] = {env: [None] * len(descriptions) for env in envs}

    for env in envs:
        env_idx = env_to_idx[env]
        for i, desc in enumerate(tqdm(descriptions, desc=f"knn[{env}]")):
            vec = stack[i, env_idx, :].tolist()
            body = {
                "size": 1,
                "_source": {"includes": ["loinc_code", "description"]},
                "query": {"knn": {"description_vector": {"vector": vec, "k": 1}}},
            }
            try:
                resp = client.search(index=index_name, body=body)
                hits = resp.get("hits", {}).get("hits", [])
                if hits:
                    top1[env][i] = hits[0]["_source"].get("loinc_code")
            except Exception as exc:  # noqa: BLE001
                print(f"  knn failed for {env}/{desc!r}: {exc}", file=sys.stderr)
    return top1


def offline_knn_top1_per_env(
    stack: np.ndarray,
    envs: list[str],
    corpus_env: str,
) -> dict[str, list[int]]:
    """In-memory KNN proxy.

    Uses `stack[:, corpus_idx, :]` as the searchable corpus and, for each env, finds
    the index of the nearest corpus vector (by cosine) for each query vector. This
    cannot detect cases where drift changes the result *relative to the full prod
    corpus* (which has ~1.7M vectors), but it does tell us whether the cross-env drift
    is large enough to change the nearest neighbor *within the test subset*, which is
    a useful sanity check.
    """
    env_to_idx = {e: i for i, e in enumerate(envs)}
    corpus = stack[:, env_to_idx[corpus_env], :]  # (N, D)
    corpus_norms = np.linalg.norm(corpus, axis=1, keepdims=True)
    corpus_unit = corpus / np.where(corpus_norms == 0, 1.0, corpus_norms)

    top1: dict[str, list[int]] = {}
    for env in envs:
        q = stack[:, env_to_idx[env], :]
        q_norms = np.linalg.norm(q, axis=1, keepdims=True)
        q_unit = q / np.where(q_norms == 0, 1.0, q_norms)
        sims = q_unit @ corpus_unit.T  # (N, N)
        top1[env] = np.argmax(sims, axis=1).tolist()
    return top1


def offline_agreement_matrix(top1: dict[str, list[int]], envs: list[str]) -> dict:
    n_desc = len(next(iter(top1.values())))
    matrix = {a: {b: 0.0 for b in envs} for a in envs}
    for a in envs:
        for b in envs:
            agree = sum(1 for i in range(n_desc) if top1[a][i] == top1[b][i])
            matrix[a][b] = agree / n_desc
    return matrix


def agreement_matrix(top1: dict[str, list[str | None]], envs: list[str]) -> dict:
    n_desc = len(next(iter(top1.values())))
    matrix = {a: {b: 0.0 for b in envs} for a in envs}
    for a in envs:
        for b in envs:
            agree = sum(
                1
                for i in range(n_desc)
                if top1[a][i] is not None
                and top1[b][i] is not None
                and top1[a][i] == top1[b][i]
            )
            valid = sum(
                1 for i in range(n_desc) if top1[a][i] is not None and top1[b][i] is not None
            )
            matrix[a][b] = agree / valid if valid else 0.0
    return matrix


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--with-knn",
        action="store_true",
        help="Run KNN queries against prod OpenSearch (requires VPC reachability).",
    )
    parser.add_argument(
        "--with-offline-knn",
        action="store_true",
        help="In-memory KNN against the azure_gpu corpus across the same 500-row subset. "
        "Cheaper proxy that works without OpenSearch access.",
    )
    args = parser.parse_args()

    print("Loading vectors...", file=sys.stderr)
    raw = {env: load_vectors(env) for env in ENVS}
    available_envs = [env for env, v in raw.items() if v]
    if len(available_envs) < 2:
        print(f"ERROR: need ≥2 envs, only found {available_envs}", file=sys.stderr)
        return 2

    coverage = {env: len(raw[env]) for env in available_envs}
    print(f"Coverage per env: {coverage}", file=sys.stderr)

    descriptions = sorted(set.intersection(*[set(raw[env].keys()) for env in available_envs]))
    print(f"Intersection: {len(descriptions)} descriptions", file=sys.stderr)

    if not descriptions:
        print("ERROR: no descriptions common to all envs", file=sys.stderr)
        return 2

    n_descs = len(descriptions)
    dim = len(next(iter(raw[available_envs[0]].values())))
    stack = np.zeros((n_descs, len(available_envs), dim), dtype=np.float64)
    for j, env in enumerate(available_envs):
        for i, desc in enumerate(descriptions):
            stack[i, j, :] = raw[env][desc]

    pair_metrics = compute_pairwise(stack, descriptions, available_envs)
    outliers = outlier_descriptions(stack, descriptions)
    smoke = self_pair_smoke_test(stack, available_envs)

    metrics = {
        "envs": available_envs,
        "n_descriptions": n_descs,
        "n_dim": dim,
        "coverage": coverage,
        "descriptions": descriptions,
        "self_pair_cosine": smoke,
        "pair_metrics": pair_metrics,
        "outliers": outliers,
    }
    metrics_path = OUTPUTS / "metrics.json"
    metrics_path.write_text(json.dumps(metrics))
    print(f"Wrote {metrics_path}", file=sys.stderr)

    if args.with_knn:
        index_name = os.environ.get("INDEX_NAME", "ttc-index")
        if "OPENSEARCH_ENDPOINT_URL" not in os.environ:
            print("ERROR: --with-knn requires OPENSEARCH_ENDPOINT_URL", file=sys.stderr)
            return 2
        top1 = knn_top1_per_env(stack, descriptions, available_envs, index_name)
        matrix = agreement_matrix(top1, available_envs)
        knn_payload = {
            "envs": available_envs,
            "descriptions": descriptions,
            "mode": "opensearch",
            "top1_by_env": top1,
            "agreement_matrix": matrix,
        }
        knn_path = OUTPUTS / "knn_top1.json"
        knn_path.write_text(json.dumps(knn_payload))
        print(f"Wrote {knn_path} (mode=opensearch)", file=sys.stderr)
    elif args.with_offline_knn:
        corpus_env = "azure_gpu" if "azure_gpu" in available_envs else available_envs[0]
        top1 = offline_knn_top1_per_env(stack, available_envs, corpus_env)
        matrix = offline_agreement_matrix(top1, available_envs)
        knn_payload = {
            "envs": available_envs,
            "descriptions": descriptions,
            "mode": "offline",
            "corpus_env": corpus_env,
            "top1_by_env": top1,
            "agreement_matrix": matrix,
        }
        knn_path = OUTPUTS / "knn_top1.json"
        knn_path.write_text(json.dumps(knn_payload))
        print(f"Wrote {knn_path} (mode=offline, corpus={corpus_env})", file=sys.stderr)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
