# load_test_report.py
#
# Metrics collection and A/B comparison for scripts/load_test.sh.
#
#   report  — for one pass of one arm: queries CloudWatch Logs Insights for
#             the two lambdas' REPORT lines (duration percentiles, cold
#             starts, init duration, memory), joins S3 LastModified times of
#             submission vs. augmented objects for end-to-end latency, and
#             checks every augmented eICR's predicted LOINC against the
#             expected code. Writes a JSON results file and prints a summary.
#   compare — prints a side-by-side delta table of two results JSON files
#             (typically baseline vs. branch). Uses only the stdlib.
#
# Invocations are attributed to the run by time window, so run the load test
# in a window with no other traffic to these lambdas; the summary warns when
# the invocation count exceeds the document count.

import argparse
import concurrent.futures
import json
import sys
import time
import xml.etree.ElementTree as ET

import boto3

TTC_LOG_GROUP = "/aws/lambda/ttc-lambda"
MAX_FAILURES_SHOWN = 10
AUG_LOG_GROUP = "/aws/lambda/ttc-augmentation-lambda"
SUBMISSION_PREFIX = "TextToCodeSubmissionV2/"
AUGMENTED_PREFIX = "AugmentationEICRV2/"

REPORT_STATS_QUERY = """
filter @type = "REPORT"
| stats count(*) as invocations,
        pct(@duration, 50) as p50_ms,
        pct(@duration, 90) as p90_ms,
        pct(@duration, 99) as p99_ms,
        max(@duration) as max_ms,
        count(@initDuration) as cold_starts,
        avg(@initDuration) as avg_init_ms,
        max(@initDuration) as max_init_ms,
        max(@maximumMemoryUsed) / 1000000 as max_mem_mb
"""

ERROR_COUNT_QUERY = r"""
filter @message like /(\[ERROR\]|Task timed out)/
| stats count(*) as errors
"""


def _run_insights_query(logs_client, log_group: str, query: str, start: int, end: int) -> dict:  # noqa: ANN001
    """Run one CloudWatch Logs Insights query and return its single stats row.

    :param logs_client: A boto3 CloudWatch Logs client.
    :param log_group: The log group to query.
    :param query: The Logs Insights query string (must produce one stats row).
    :param start: Window start (epoch seconds).
    :param end: Window end (epoch seconds).
    :returns: The stats row as a field-name -> float mapping (empty if no data).
    """
    query_id = logs_client.start_query(
        logGroupName=log_group, startTime=start, endTime=end, queryString=query
    )["queryId"]
    deadline = time.time() + 120
    while time.time() < deadline:
        response = logs_client.get_query_results(queryId=query_id)
        if response["status"] not in ("Scheduled", "Running"):
            break
        time.sleep(2)
    if response["status"] != "Complete":
        print(f"  WARNING: Logs Insights query on {log_group} ended {response['status']}")
        return {}
    if not response["results"]:
        return {}
    return {
        field["field"]: round(float(field["value"]), 1)
        for field in response["results"][0]
        if field["value"] is not None
    }


def _list_last_modified(s3_client, bucket: str, prefix: str) -> dict[str, float]:  # noqa: ANN001
    """Map object basename -> LastModified epoch seconds for a prefix.

    :param s3_client: A boto3 S3 client.
    :param bucket: The bucket to list.
    :param prefix: The full key prefix to list under.
    :returns: A mapping of key basename to LastModified as epoch seconds.
    """
    out: dict[str, float] = {}
    paginator = s3_client.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        for obj in page.get("Contents", []):
            out[obj["Key"].rsplit("/", 1)[-1]] = obj["LastModified"].timestamp()
    return out


def _predicted_loinc(xml: str) -> str | None:
    """Extract the predicted LOINC translation code from an augmented eICR.

    Mirrors bash_xml_parser.py: the first observation code's <translation>
    is where the TTC pipeline writes its predicted standardization.

    :param xml: The augmented eICR XML text.
    :returns: The predicted LOINC code, or None if no translation was added.
    """
    node = ET.fromstring(xml).find(
        "{*}component/{*}structuredBody/{*}component/{*}section/{*}entry/"
        "{*}observation/{*}code/{*}translation"
    )
    return None if node is None else node.get("code")


def _percentile(values: list[float], q: float) -> float | None:
    """Nearest-rank percentile of a list of values.

    :param values: The sample values (need not be sorted).
    :param q: The percentile as a fraction (e.g. 0.5 for p50).
    :returns: The percentile value, or None for an empty sample.
    """
    if not values:
        return None
    ordered = sorted(values)
    return round(ordered[min(len(ordered) - 1, round(q * (len(ordered) - 1)))], 1)


def run_report(args: argparse.Namespace) -> int:
    """Collect metrics for one pass and write the results JSON.

    :param args: Parsed CLI arguments for the report subcommand.
    :returns: Process exit code.
    """
    with open(args.manifest) as fp:
        manifest = json.load(fp)
    docs = [d for d in manifest["docs"] if d["pass"] == args.pass_label]
    if not docs:
        print(f"No documents for pass {args.pass_label} in {args.manifest}", file=sys.stderr)
        return 1
    run_id, arm = manifest["run_id"], manifest["arm"]
    run_prefix = f"loadtest_{run_id}_{arm}_{args.pass_label}_"

    logs = boto3.client("logs", region_name=args.region)
    s3 = boto3.client("s3", region_name=args.region)

    lambda_stats = {}
    for label, group in (("ttc_lambda", TTC_LOG_GROUP), ("augmentation_lambda", AUG_LOG_GROUP)):
        stats = _run_insights_query(logs, group, REPORT_STATS_QUERY, args.start, args.end)
        errors = _run_insights_query(logs, group, ERROR_COUNT_QUERY, args.start, args.end)
        stats["errors"] = errors.get("errors", 0)
        lambda_stats[label] = stats

    submitted = _list_last_modified(s3, args.bucket, SUBMISSION_PREFIX + run_prefix)
    augmented = _list_last_modified(s3, args.bucket, AUGMENTED_PREFIX + run_prefix)
    e2e_latencies = [augmented[name] - submitted[name] for name in augmented if name in submitted]

    def check_doc(doc: dict) -> dict:
        """Fetch one augmented eICR and compare its predicted LOINC to expected.

        :param doc: The manifest entry for the document.
        :returns: The manifest entry annotated with predicted code and status.
        """
        if doc["filename"] not in augmented:
            return {**doc, "predicted_loinc": None, "status": "missing"}
        body = s3.get_object(Bucket=args.bucket, Key=AUGMENTED_PREFIX + doc["filename"])
        predicted = _predicted_loinc(body["Body"].read().decode("utf-8"))
        status = "match" if predicted == doc["expected_loinc"] else "mismatch"
        return {**doc, "predicted_loinc": predicted, "status": status}

    with concurrent.futures.ThreadPoolExecutor(max_workers=16) as pool:
        checked = list(pool.map(check_doc, docs))

    matches = sum(1 for d in checked if d["status"] == "match")
    failures = [
        {
            "filename": d["filename"],
            "base_input": d["base_input"],
            "expected_loinc": d["expected_loinc"],
            "predicted_loinc": d["predicted_loinc"],
            "status": d["status"],
        }
        for d in checked
        if d["status"] != "match"
    ]

    results = {
        "run_id": run_id,
        "arm": arm,
        "pass": args.pass_label,
        "window": {"start": args.start, "end": args.end},
        "documents": len(docs),
        "ttc_lambda": lambda_stats["ttc_lambda"],
        "augmentation_lambda": lambda_stats["augmentation_lambda"],
        "end_to_end_s": {
            "completed": len(e2e_latencies),
            "p50": _percentile(e2e_latencies, 0.50),
            "p90": _percentile(e2e_latencies, 0.90),
            "p99": _percentile(e2e_latencies, 0.99),
            "max": _percentile(e2e_latencies, 1.0),
        },
        "correctness": {
            "expected": len(docs),
            "loinc_matches": matches,
            "match_rate": round(matches / len(docs), 4),
            "failures": failures,
        },
    }
    with open(args.out, "w") as fp:
        json.dump(results, fp, indent=2)

    print(f"\n=== {arm} / {args.pass_label} — {len(docs)} documents ===")
    for label in ("ttc_lambda", "augmentation_lambda"):
        s = lambda_stats[label]
        if not s:
            print(f"  {label}: no REPORT lines found in window")
            continue
        print(
            f"  {label}: {s.get('invocations', 0):.0f} invocations, "
            f"p50 {s.get('p50_ms')}ms / p90 {s.get('p90_ms')}ms / p99 {s.get('p99_ms')}ms, "
            f"{s.get('cold_starts', 0):.0f} cold starts (avg init {s.get('avg_init_ms')}ms), "
            f"max mem {s.get('max_mem_mb')}MB, errors {s.get('errors'):.0f}"
        )
        if s.get("invocations", 0) > len(docs):
            print(
                f"  WARNING: {label} ran {s['invocations']:.0f} times for {len(docs)} documents "
                "— other traffic or retries in the window; treat duration stats with care"
            )
    e2e = results["end_to_end_s"]
    print(
        f"  end-to-end: {e2e['completed']}/{len(docs)} completed, "
        f"p50 {e2e['p50']}s / p90 {e2e['p90']}s / max {e2e['max']}s"
    )
    print(f"  correctness: {matches}/{len(docs)} predicted LOINC matches expected")
    for f in failures[:MAX_FAILURES_SHOWN]:
        print(
            f"    {f['status']}: '{f['base_input']}' "
            f"expected {f['expected_loinc']} got {f['predicted_loinc']}"
        )
    if len(failures) > MAX_FAILURES_SHOWN:
        print(f"    ... and {len(failures) - MAX_FAILURES_SHOWN} more (see {args.out})")
    print(f"  results written to {args.out}")
    return 0


def run_compare(args: argparse.Namespace) -> int:
    """Print a side-by-side delta table of two results JSON files.

    :param args: Parsed CLI arguments for the compare subcommand.
    :returns: Process exit code.
    """
    with open(args.a) as fp:
        a = json.load(fp)
    with open(args.b) as fp:
        b = json.load(fp)

    def rows(results: dict) -> dict[str, float | None]:
        """Flatten one results JSON into the comparison metrics.

        :param results: A results JSON as written by the report subcommand.
        :returns: Metric name -> value.
        """
        ttc, aug, e2e = (
            results["ttc_lambda"],
            results["augmentation_lambda"],
            results["end_to_end_s"],
        )
        return {
            "ttc p50 (ms)": ttc.get("p50_ms"),
            "ttc p90 (ms)": ttc.get("p90_ms"),
            "ttc p99 (ms)": ttc.get("p99_ms"),
            "ttc max (ms)": ttc.get("max_ms"),
            "ttc cold starts": ttc.get("cold_starts"),
            "ttc avg init (ms)": ttc.get("avg_init_ms"),
            "ttc max init (ms)": ttc.get("max_init_ms"),
            "ttc max mem (MB)": ttc.get("max_mem_mb"),
            "ttc errors": ttc.get("errors"),
            "aug p50 (ms)": aug.get("p50_ms"),
            "aug p90 (ms)": aug.get("p90_ms"),
            "end-to-end p50 (s)": e2e.get("p50"),
            "end-to-end p90 (s)": e2e.get("p90"),
            "end-to-end max (s)": e2e.get("max"),
            "completed docs": e2e.get("completed"),
            "LOINC match rate": results["correctness"].get("match_rate"),
        }

    label_a = f"{a['arm']}/{a['pass']}"
    label_b = f"{b['arm']}/{b['pass']}"
    print(f"\n{'metric':<22} {label_a:>14} {label_b:>14} {'delta':>10} {'delta %':>9}")
    print("-" * 74)
    rows_a, rows_b = rows(a), rows(b)
    for metric in rows_a:
        va, vb = rows_a[metric], rows_b[metric]
        if va is None or vb is None:
            print(f"{metric:<22} {va!s:>14} {vb!s:>14} {'—':>10} {'—':>9}")
            continue
        delta = round(vb - va, 1)
        pct = f"{delta / va * 100:+.1f}%" if va else "—"
        print(f"{metric:<22} {va:>14} {vb:>14} {delta:>+10} {pct:>9}")
    print()
    return 0


def main() -> int:
    """Run the report or compare subcommand."""
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    report = sub.add_parser("report", help="Collect metrics for one pass of one arm")
    report.add_argument("--manifest", required=True, help="Path to the corpus manifest.json")
    report.add_argument("--pass", dest="pass_label", required=True, help="Pass label (e.g. p1)")
    report.add_argument("--start", type=int, required=True, help="Window start (epoch seconds)")
    report.add_argument("--end", type=int, required=True, help="Window end (epoch seconds)")
    report.add_argument("--bucket", required=True, help="S3 bucket the pipeline ran against")
    report.add_argument("--region", default="us-east-2", help="AWS region")
    report.add_argument("--out", required=True, help="Path to write the results JSON")

    compare = sub.add_parser("compare", help="Diff two results JSON files")
    compare.add_argument("a", help="Baseline results JSON")
    compare.add_argument("b", help="Comparison results JSON")

    args = parser.parse_args()
    return run_report(args) if args.command == "report" else run_compare(args)


if __name__ == "__main__":
    raise SystemExit(main())
