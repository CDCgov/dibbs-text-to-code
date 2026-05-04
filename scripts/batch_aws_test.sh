#!/usr/bin/env bash
#
# A batch-uploading bulk testing script for the DIBBs TTC Pipeline.

# Given a JSON file of nonstandard test cases, this script:
#   1. Loads each test case from the file into a bash array.
#   2. Templates a dummy test eICR with the nonstandard input name
#      of each test case, and stamps each result with a fresh UUID.
#   3. For each test eICR, one at a time, uploads the templated eICR + a 
#      canned schematron errors file to S3, which fires the TTC lambda
#      via SQS event.
#   4. Tails both lambdas' CloudWatch logs in real time until each emits its
#      `REPORT RequestId:` line (AWS's end-of-invocation marker).
#   5. Fetches the resulting augmented eICR XML from S3, parses its
#      translated code name (where the TTC Pipeline leaves its predicted
#      standardization), and compares the result to the expected value of
#      the test case.

# Usage: ./scripts/batch_aws_test.sh ./test_cases_file.json
#

set -euo pipefail

# ── Required tooling ──────────────────────────────────────────────────────────
# gum:      TUI chrome (styled banners, spinners, log levels).
command -v gum >/dev/null || {
    echo "This script requires 'gum'. Install with: brew install gum" >&2
    exit 1
}


# ── Config ────────────────────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BUCKET="dibbs-text-to-code"
SOURCE_EICR="$SCRIPT_DIR/test_eicr.xml"
SOURCE_SCHEMATRON="$SCRIPT_DIR/test_schematron_errors.xml"
TTC_LOG="/aws/lambda/ttc-lambda"                  # CloudWatch log group for the TTC lambda
AUG_LOG="/aws/lambda/ttc-augmentation-lambda"     # …and the augmentation lambda
AWS_REGION="us-east-2"


# ── Chrome helpers ────────────────────────────────────────────────────────────

# Purple bold section header with a blank line above it.
section() { gum style --foreground=99 --bold --margin="1 0 0 0" "▸ $*"; }


# ── Argument + input validation ───────────────────────────────────────────────

[[ $# -eq 1 ]] || {
    gum style --foreground=red --bold "Usage: $0 \"<path to JSON file of nonstandard cases>\""
    exit 1
}
JSON_FP="$1"

[[ -f "$SOURCE_EICR" ]] || {
    gum log -l error "Missing $SOURCE_EICR"
    exit 1
}
[[ -f "$SOURCE_SCHEMATRON" ]] || {
    gum log -l error "Missing $SOURCE_SCHEMATRON"
    exit 1
}


# ── Per-run state ─────────────────────────────────────────────────────────────
# The same FILENAME is reused across every S3 prefix — that's how the TTC
# and augmentation lambdas correlate the schematron report, the source eICR,
# and the resulting metadata/output objects for one invocation.
TMPDIR="$(mktemp -d)"
trap 'rm -rf "$TMPDIR"' EXIT

gum style --border=rounded --padding="0 2" --margin="1 0" --foreground=212 --bold \
    "DIBBs Text to Code Batch Pipeline Test" "" \
    "File of Test Cases: $JSON_FP" \
    "Bucket:    s3://$BUCKET" \


# ── Log-tail phase ────────────────────────────────────────────────────────────
#
# Tail a CloudWatch log group until its `REPORT RequestId:` line appears
# (Lambda's end-of-invocation marker).
#
# The loop reads from a FIFO on FD 3 with a 100 ms `read -t` timeout so we
# can animate the spinner while waiting for the next log event. `rc > 128`
# means the read timed out (vs a real EOF, which breaks the loop).
follow_until_report() {
    local log_group="$1" label="$2" start fifo tail_pid line rc
    start=$(date +%s)
    fifo="$(mktemp -u)"
    mkfifo "$fifo"

    # Start the tail in the background; read its output from FD 3 so we can
    # use `read -t` on it (needs a persistent FD, not a redirect per-read).
    aws logs tail "$log_group" --region "$AWS_REGION" --follow --since "${start}s" --color off >"$fifo" &
    tail_pid=$!
    exec 3<"$fifo"

    while :; do
        if IFS= read -r -t 1 -u 3 line; then
            [[ "$line" == *"REPORT RequestId:"* ]] && break
        else
            rc=$?
            (( rc > 128 )) || break   # rc > 128 = timeout; anything else = EOF
        fi
    done

    exec 3<&-
    kill "$tail_pid" 2>/dev/null || true
    wait "$tail_pid" 2>/dev/null || true
    rm -f "$fifo"

    echo "  $label complete in $(( $(date +%s) - start ))s"
}


wait_for_s3_object() {
    local key="$1" label="$2" timeout="${3:-120}" interval=2 elapsed=0

    while ! aws s3api head-object --region "$AWS_REGION" --bucket "$BUCKET" --key "$key" >/dev/null 2>&1; do
        if (( elapsed >= timeout )); then
            gum log -l error "Timed out waiting for $label at s3://$BUCKET/$key"
            return 1
        fi

        printf '\r\033[K'
        elapsed=$((elapsed + interval))
    done
}


# ── Load Test Cases ───────────────────────────────────────────────────────────
# Open up the filepath to the given JSON list of cases and read them.
# No native support for JSON in bash scripting, but we can just use python.
# The test cases JSON file has some nested structuring to make it easy to
# define new cases or modify existing ones, so the easiest way to programmatically
# handle this is to use a simple helper script with a few lines of python that
# loads the appropriate variable within the nested structure.
NONSTANDARD_INPUTS=(); CORRECT_OUTPUTS=(); LOINC_CODES=()
while IFS=$'\t' read -r nin cout loinc; do
    NONSTANDARD_INPUTS+=("$nin"); CORRECT_OUTPUTS+=("$cout"); LOINC_CODES+=("$loinc")
done < <(JSON_FP="$JSON_FP" python3 "$SCRIPT_DIR/bash_json_loader.py")

for i in "${!NONSTANDARD_INPUTS[@]}"; do

    section "Test Case $i:"
    FILENAME="$(date +%m-%d-%Y_%H:%M:%S)_$i.xml"
    TEMPLATED_EICR="$TMPDIR/$FILENAME"

    # ── Template the eICR ─────────────────────────────────────────────────────────
    # Rewrite the first displayName + originalText with this nonstandard in so the TTC
    # pipeline has a unique text candidate to resolve, and stamp fresh UUIDs on
    # <id>/<setId> so this eICR looks like a new document to downstream systems.
    echo "  Templating eICR with nonstandard input '${NONSTANDARD_INPUTS[$i]}'"
    INPUT="${NONSTANDARD_INPUTS[$i]}" SOURCE_EICR="$SOURCE_EICR" OUT_PATH="$TEMPLATED_EICR" \
        python3 "$SCRIPT_DIR/bash_eicr_templater.py"
    
    
    # # ── Fire the pipeline ─────────────────────────────────────────────────────────
    # # The schematron report must land under ValidationResponseV2/ before the eICR
    # # under TextToCodeSubmissionV2/, because the eICR put is the S3 event that
    # # triggers the TTC lambda, which then reads the paired schematron report by
    # # the same filename.
    echo "  Uploading to S3"
    gum spin --spinner=dot --title "Uploading schematron errors…" -- \
        aws s3 cp --region "$AWS_REGION" "$SOURCE_SCHEMATRON" "s3://$BUCKET/ValidationResponseV2/$FILENAME"
    gum spin --spinner=dot --title "Uploading templated eICR…" -- \
        aws s3 cp --region "$AWS_REGION" "$TEMPLATED_EICR" "s3://$BUCKET/TextToCodeSubmissionV2/$FILENAME"

    # Block until each lambda finishes. TTC writes TTCAugmentationMetadataV2/<name>.json,
    # which triggers the augmentation lambda; that's why we watch them in sequence.
    follow_until_report "$TTC_LOG" "TTC"
    follow_until_report "$AUG_LOG" "Augmentation"


    # ── Parse the outputs ──────────────────────────────────────────────────────────
    echo "  Fetching results..."
    wait_for_s3_object "AugmentationEICRV2/$FILENAME" "augmented eICR"
    content="$(aws s3 cp --region "$AWS_REGION" "s3://$BUCKET/AugmentationEICRV2/$FILENAME" -)"
    { read PREDICTED_LOINC; read PREDICTED_CODE_STRING; } < <(CONTENT="$content" python3 "$SCRIPT_DIR/bash_xml_parser.py")

    if [[ "$PREDICTED_LOINC" = "${LOINC_CODES[$i]}" ]]; then
        echo "  Predicted LOINC code $PREDICTED_LOINC matches expected code ${LOINC_CODES[$i]}"
        echo "  Test Case Passed!"
    else
        echo "  Predicted code $PREDICTED_LOINC does not match expected code ${LOINC_CODES[$i]}"
        echo "    Predicted code string: $PREDICTED_CODE_STRING"
        echo "    Expected code string:  ${CORRECT_OUTPUTS[$i]}"
        echo "  Test Case Failed :/"
    fi

done
