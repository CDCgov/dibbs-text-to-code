"""Re-embed the LOINC description subset on this machine.

Mirrors `text_to_code.services.embedder` but passes `device` explicitly so we can
compare CPU vs. MPS outputs on Apple Silicon. Writes a `{description: [floats]}` JSON
file with the same shape as `~/Downloads/cpu_vector_test.json`.

MPS failures (unsupported ops, kernel errors) are caught per-item and logged so a
single bad description doesn't abort the run.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from sentence_transformers import SentenceTransformer
from tqdm import tqdm

MODEL_ID = "NCHS/ttc-retriever-v1.0"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--device", choices=["cpu", "mps"], required=True)
    parser.add_argument(
        "--inputs",
        type=Path,
        required=True,
        help="JSON file whose top-level keys are the descriptions to embed.",
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--failures",
        type=Path,
        default=None,
        help="Where to write per-item failures (default: alongside --output as *_failures.json).",
    )
    args = parser.parse_args()

    descs = list(json.loads(args.inputs.read_text()).keys())
    print(f"Loaded {len(descs)} descriptions from {args.inputs}", file=sys.stderr)

    print(f"Loading {MODEL_ID} on device={args.device}", file=sys.stderr)
    model = SentenceTransformer(MODEL_ID, device=args.device)

    vectors: dict[str, list[float]] = {}
    failures: list[dict[str, str]] = []

    for desc in tqdm(descs, desc=f"embed ({args.device})"):
        try:
            vec = model.encode(desc)
            vectors[desc] = vec.tolist()
        except Exception as exc:  # noqa: BLE001 - per-item resilience is the point
            failures.append({"description": desc, "error": f"{type(exc).__name__}: {exc}"})

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(vectors))
    print(f"Wrote {len(vectors)} vectors to {args.output}", file=sys.stderr)

    if failures:
        failures_path = args.failures or args.output.with_name(
            f"{args.output.stem}_failures.json"
        )
        failures_path.write_text(json.dumps(failures, indent=2))
        print(
            f"WARNING: {len(failures)}/{len(descs)} items failed; details in {failures_path}",
            file=sys.stderr,
        )
        if len(failures) / max(len(descs), 1) > 0.05:
            print(
                "More than 5% of items failed; drop this env from analyze.py if needed.",
                file=sys.stderr,
            )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
