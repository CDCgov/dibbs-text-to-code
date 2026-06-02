"""Embed a batch of LOINC descriptions inside the prod Lambda container.

Reads `/work/inputs.json` (a `{description: ...}` dict — values are ignored, only keys
matter), embeds each description with the same `SentenceTransformer` model the Lambda
loads at cold start, and writes `/work/vectors_aws_lambda.json`.

Runs against the model baked into the Lambda image at `/opt/retriever_model`
(overridable via `RETRIEVER_MODEL_PATH`).
"""

from __future__ import annotations

import json
import os
import sys

from sentence_transformers import SentenceTransformer

INPUT_PATH = os.environ.get("INPUT_PATH", "/work/inputs.json")
OUTPUT_PATH = os.environ.get("OUTPUT_PATH", "/work/vectors_aws_lambda.json")
MODEL_PATH = os.environ.get("RETRIEVER_MODEL_PATH", "/opt/retriever_model")


def main() -> int:
    with open(INPUT_PATH) as fh:
        descs = list(json.load(fh).keys())
    print(f"Loaded {len(descs)} descriptions from {INPUT_PATH}", file=sys.stderr)

    print(f"Loading model from {MODEL_PATH}", file=sys.stderr)
    model = SentenceTransformer(MODEL_PATH)

    vectors: dict[str, list[float]] = {}
    for i, desc in enumerate(descs, 1):
        vectors[desc] = model.encode(desc).tolist()
        if i % 50 == 0 or i == len(descs):
            print(f"  embedded {i}/{len(descs)}", file=sys.stderr)

    with open(OUTPUT_PATH, "w") as fh:
        json.dump(vectors, fh)
    print(f"Wrote {len(vectors)} vectors to {OUTPUT_PATH}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
