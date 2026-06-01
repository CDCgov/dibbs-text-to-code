"""Pull `description_vector` for each input description from the OSIS ingestion NDJSON.

The prod OpenSearch domain is VPC-only, so the original `fetch_azure_gpu.py` only
works from inside the VPC. The same vectors are also available at
`s3://dibbs-text-to-code/ingestion/*.jsonl` (the source files OSIS bulk-loads into
the index), and S3 is reachable from anywhere with AWS creds. This script streams
those files in parallel and pulls out exactly the descriptions we need.

Env / args required:
- AWS credentials with `s3:GetObject` on the bucket (default: `dibbs-text-to-code`).
- AWS_REGION (default us-east-2).
"""

from __future__ import annotations

import argparse
import json
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import boto3
from tqdm import tqdm

DEFAULT_BUCKET = "dibbs-text-to-code"
DEFAULT_PREFIX = "ingestion/"


def list_files(s3, bucket: str, prefix: str) -> list[str]:
    keys = []
    paginator = s3.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        for obj in page.get("Contents", []):
            key = obj["Key"]
            if key.endswith(".jsonl") or key.endswith(".ndjson"):
                keys.append(key)
    return keys


def scan_one_file(
    s3,
    bucket: str,
    key: str,
    wanted: set[str],
    results: dict[str, list[float]],
    found_lock: threading.Lock,
) -> int:
    """Stream a single NDJSON file, capturing vectors for any wanted descriptions."""
    found_here = 0
    body = s3.get_object(Bucket=bucket, Key=key)["Body"]
    for line in body.iter_lines():
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        desc = row.get("description")
        if desc in wanted:
            with found_lock:
                if desc not in results:
                    results[desc] = row.get("description_vector")
                    found_here += 1
    return found_here


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inputs", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--bucket", default=DEFAULT_BUCKET)
    parser.add_argument("--prefix", default=DEFAULT_PREFIX)
    parser.add_argument("--workers", type=int, default=16)
    parser.add_argument(
        "--misses",
        type=Path,
        default=None,
        help="Where to write descriptions not found (default: outputs/azure_gpu_misses.json).",
    )
    args = parser.parse_args()

    descs = list(json.loads(args.inputs.read_text()).keys())
    wanted = set(descs)
    print(f"Looking for {len(wanted)} descriptions in s3://{args.bucket}/{args.prefix}", file=sys.stderr)

    s3 = boto3.client("s3")
    keys = list_files(s3, args.bucket, args.prefix)
    print(f"Scanning {len(keys)} NDJSON files with {args.workers} workers", file=sys.stderr)

    results: dict[str, list[float]] = {}
    found_lock = threading.Lock()

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {
            pool.submit(scan_one_file, s3, args.bucket, k, wanted, results, found_lock): k
            for k in keys
        }
        with tqdm(total=len(futures), desc="scan") as pbar:
            for fut in as_completed(futures):
                fut.result()
                pbar.set_postfix(found=len(results))
                pbar.update(1)
                if len(results) == len(wanted):
                    # Cancel any not-yet-started futures.
                    for f, _ in futures.items():
                        f.cancel()
                    break

    misses = sorted(wanted - results.keys())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(results))
    misses_path = args.misses or args.output.with_name("azure_gpu_misses.json")
    misses_path.write_text(json.dumps(misses, indent=2))

    hit_rate = len(results) / max(len(wanted), 1)
    print(
        f"Wrote {len(results)} vectors to {args.output} "
        f"({hit_rate:.1%} coverage; {len(misses)} misses in {misses_path})",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
