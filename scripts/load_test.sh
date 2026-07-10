#!/usr/bin/env bash
#
# A/B load test for the deployed DIBBs TTC pipeline.
#
# Unlike batch_aws_test.sh (serial, one warm container, functional gate),
# this script templates a corpus of a few hundred salted eICRs, uploads them
# to S3 in a parallel burst to force Lambda scale-out (SQS batch_size=1, no
# reserved concurrency), waits for the pipeline to drain, and then measures
# from CloudWatch REPORT lines and S3 timestamps rather than by log-tailing:
#
#   - per-invocation duration percentiles, cold-start count, init duration,
#     and max memory for both lambdas (CloudWatch Logs Insights)
#   - end-to-end latency per document (S3 LastModified: submission -> augmented)
#   - correctness: every augmented eICR's predicted LOINC vs. the expected code
#
# Every candidate text is salted with a unique run/arm/index marker, so the
# TTC result cache (keyed by hash of the text) never hits across runs or
# arms — no OpenSearch access needed to reset state. With --passes 2, the
# second pass repeats the same salted texts under fresh filenames/UUIDs to
# measure the warm result-cache path as well.
#
# A/B protocol:
#   1. Deploy the baseline (main) image, then:  ./scripts/load_test.sh run --arm baseline
#   2. Deploy the branch image, then:           ./scripts/load_test.sh run --arm branch
#   3. ./scripts/load_test.sh compare load_test_runs/<id>-baseline/results_p1.json \
#                                      load_test_runs/<id>-branch/results_p1.json
#
# Run each arm in a window with no other traffic to the lambdas; invocations
# are attributed by time window and the report warns if counts don't line up.
#
# Usage:
#   ./scripts/load_test.sh run --arm <label> [--docs 300] [--passes 1]
#       [--concurrency 24] [--cases scripts/test_cases.json]
#       [--bucket dibbs-text-to-code] [--out-dir load_test_runs]
#       [--drain-timeout 1800]
#   ./scripts/load_test.sh compare <baseline results.json> <branch results.json>

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
AWS_REGION="us-east-2"
SETTLE_SECONDS=90   # CloudWatch Logs ingestion lag before querying Insights

command -v aws >/dev/null || { echo "This script requires the AWS CLI." >&2; exit 1; }
command -v uv >/dev/null || { echo "This script requires 'uv'. Install: https://docs.astral.sh/uv/" >&2; exit 1; }

usage() {
    sed -n '2,40p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
    exit 1
}

run_py() {
    uv run --project "$REPO_ROOT" --all-packages python "$@"
}

[[ $# -ge 1 ]] || usage
COMMAND="$1"; shift

# ── compare ───────────────────────────────────────────────────────────────────
if [[ "$COMMAND" == "compare" ]]; then
    [[ $# -eq 2 ]] || usage
    exec uv run --project "$REPO_ROOT" --all-packages python "$SCRIPT_DIR/load_test_report.py" compare "$1" "$2"
fi
[[ "$COMMAND" == "run" ]] || usage

# ── run: argument parsing ─────────────────────────────────────────────────────
ARM="" DOCS=300 PASSES=1 CONCURRENCY=24 DRAIN_TIMEOUT=1800
CASES="$SCRIPT_DIR/test_cases.json"
BUCKET="dibbs-text-to-code"
OUT_ROOT="$REPO_ROOT/load_test_runs"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --arm)           ARM="$2"; shift 2 ;;
        --docs)          DOCS="$2"; shift 2 ;;
        --passes)        PASSES="$2"; shift 2 ;;
        --concurrency)   CONCURRENCY="$2"; shift 2 ;;
        --cases)         CASES="$2"; shift 2 ;;
        --bucket)        BUCKET="$2"; shift 2 ;;
        --out-dir)       OUT_ROOT="$2"; shift 2 ;;
        --drain-timeout) DRAIN_TIMEOUT="$2"; shift 2 ;;
        *) echo "Unknown argument: $1" >&2; usage ;;
    esac
done

[[ -n "$ARM" ]] || { echo "--arm is required (e.g. --arm baseline)" >&2; exit 1; }
[[ "$ARM" =~ ^[a-z0-9-]+$ ]] || { echo "--arm must be lowercase alphanumeric/hyphens (used in S3 keys)" >&2; exit 1; }
(( DOCS >= 1 && DOCS <= 900 )) || { echo "--docs must be 1..900 (S3 list paging + SQS sanity bound)" >&2; exit 1; }
[[ -f "$CASES" ]] || { echo "Missing test cases file: $CASES" >&2; exit 1; }

RUN_ID="$(uuidgen | tr '[:upper:]' '[:lower:]' | cut -c1-8)"
OUT="$OUT_ROOT/$RUN_ID-$ARM"
mkdir -p "$OUT"

echo "DIBBs TTC load test"
echo "  run id:      $RUN_ID"
echo "  arm:         $ARM"
echo "  documents:   $DOCS per pass, $PASSES pass(es)"
echo "  concurrency: $CONCURRENCY parallel uploads"
echo "  bucket:      s3://$BUCKET"
echo "  output:      $OUT"

# ── corpus generation (local, one Saxon process) ──────────────────────────────
echo
echo "Generating corpus..."
run_py "$SCRIPT_DIR/load_test_corpus.py" \
    --cases "$CASES" --source-eicr "$SCRIPT_DIR/test_eicr.xml" \
    --out-dir "$OUT" --docs "$DOCS" --passes "$PASSES" \
    --run-id "$RUN_ID" --arm "$ARM"

upload_all() {
    local list_file="$1" local_dir="$2" s3_prefix="$3"
    xargs -P "$CONCURRENCY" -I{} \
        aws s3 cp --only-show-errors --region "$AWS_REGION" \
        "$local_dir/{}" "s3://$BUCKET/$s3_prefix/{}" <"$list_file"
}

count_augmented() {
    # `aws s3 ls` exits non-zero when the prefix has no matches yet, which
    # would abort the drain poll under `set -o pipefail` — mask it.
    { aws s3 ls --region "$AWS_REGION" \
        "s3://$BUCKET/AugmentationEICRV2/loadtest_${RUN_ID}_${ARM}_${1}_" 2>/dev/null || true; } \
        | wc -l | tr -d ' '
}

for (( PASS_NUM=1; PASS_NUM<=PASSES; PASS_NUM++ )); do
    PASS="p$PASS_NUM"
    FILES="$OUT/files_$PASS.txt"
    EXPECTED="$(wc -l <"$FILES" | tr -d ' ')"

    echo
    echo "Pass $PASS: uploading $EXPECTED schematron reports..."
    # Reports must all land under ValidationResponseV2/ before any eICR is
    # uploaded — the eICR put is the S3 event that triggers the TTC lambda,
    # which reads the paired report by the same filename.
    upload_all "$FILES" "$OUT/reports" "ValidationResponseV2"

    echo "Pass $PASS: uploading $EXPECTED eICRs (burst, $CONCURRENCY-way)..."
    T0="$(date +%s)"
    upload_all "$FILES" "$OUT/eicrs" "TextToCodeSubmissionV2"
    echo "Pass $PASS: burst uploaded in $(( $(date +%s) - T0 ))s; waiting for the pipeline to drain..."

    while :; do
        DONE_COUNT="$(count_augmented "$PASS")"
        ELAPSED=$(( $(date +%s) - T0 ))
        printf '\r  %s/%s augmented eICRs (%ss elapsed)' "$DONE_COUNT" "$EXPECTED" "$ELAPSED"
        if (( DONE_COUNT >= EXPECTED )); then echo; break; fi
        if (( ELAPSED >= DRAIN_TIMEOUT )); then
            echo
            echo "  WARNING: drain timed out after ${DRAIN_TIMEOUT}s with $DONE_COUNT/$EXPECTED complete."
            echo "  Continuing to the report — incomplete delivery is itself a finding."
            break
        fi
        sleep 10
    done

    echo "  waiting ${SETTLE_SECONDS}s for CloudWatch Logs ingestion..."
    sleep "$SETTLE_SECONDS"

    run_py "$SCRIPT_DIR/load_test_report.py" report \
        --manifest "$OUT/manifest.json" --pass "$PASS" \
        --start "$(( T0 - 30 ))" --end "$(date +%s)" \
        --bucket "$BUCKET" --region "$AWS_REGION" \
        --out "$OUT/results_$PASS.json"
done

echo
echo "Done. Compare arms with:"
echo "  ./scripts/load_test.sh compare <baseline>/results_p1.json $OUT/results_p1.json"
