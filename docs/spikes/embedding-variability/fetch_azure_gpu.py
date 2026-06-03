"""Pull `description_vector` for each input description from the prod OpenSearch index.

The production index field `description` is plain `text` (no `.keyword` subfield), so we
use `match_phrase` and post-filter on exact string equality against `_source.description`.
Any description that doesn't return a 1:1 hit is recorded as a miss.

Env vars required (same contract as the prod Lambda):
- OPENSEARCH_ENDPOINT_URL
- AWS_REGION
- INDEX_NAME (e.g. "ttc-index")
plus standard AWS credentials with `es:ESHttpGet` on the domain.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from tqdm import tqdm

from lambda_handler.lambda_handler import create_opensearch_client


def fetch_vector(client, index: str, desc: str) -> list[float] | None:
    body = {
        "size": 5,
        "query": {"match_phrase": {"description": desc}},
        "_source": ["description", "description_vector"],
    }
    response = client.search(index=index, body=body)
    for hit in response.get("hits", {}).get("hits", []):
        src = hit.get("_source", {})
        if src.get("description") == desc:
            vector = src.get("description_vector")
            if isinstance(vector, list) and vector:
                return vector
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--inputs",
        type=Path,
        required=True,
        help="JSON file whose top-level keys are the descriptions to look up.",
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--misses",
        type=Path,
        default=None,
        help="Where to write the list of descriptions not found (default: outputs/azure_gpu_misses.json).",
    )
    args = parser.parse_args()

    index = os.environ.get("INDEX_NAME", "ttc-index")
    if "OPENSEARCH_ENDPOINT_URL" not in os.environ:
        print("ERROR: OPENSEARCH_ENDPOINT_URL is not set", file=sys.stderr)
        return 2

    descs = list(json.loads(args.inputs.read_text()).keys())
    print(f"Loaded {len(descs)} descriptions; querying index={index!r}", file=sys.stderr)

    client = create_opensearch_client()

    vectors: dict[str, list[float]] = {}
    misses: list[str] = []

    for desc in tqdm(descs, desc="fetch azure_gpu"):
        vec = fetch_vector(client, index, desc)
        if vec is None:
            misses.append(desc)
        else:
            vectors[desc] = vec

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(vectors))
    misses_path = args.misses or args.output.with_name("azure_gpu_misses.json")
    misses_path.write_text(json.dumps(misses, indent=2))

    hit_rate = len(vectors) / max(len(descs), 1)
    print(
        f"Wrote {len(vectors)} vectors to {args.output} "
        f"({hit_rate:.1%} coverage; {len(misses)} misses in {misses_path})",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
