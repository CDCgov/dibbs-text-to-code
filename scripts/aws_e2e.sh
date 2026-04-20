#!/usr/bin/env bash
#
# End-to-end smoke test for the deployed DIBBs TTC pipeline.
#
# Given a "nonstandard test name" (e.g. "Zucchini IgG"), this script:
#   1. Templates scripts/test_eicr.xml with that name and fresh UUIDs.
#   2. Uploads the templated eICR + a canned schematron errors file to S3,
#      which fires the TTC lambda via SQS event.
#   3. Tails both lambdas' CloudWatch logs in real time until each emits its
#      `REPORT RequestId:` line (AWS's end-of-invocation marker).
#   4. Fetches and pretty-prints the resulting TTC metadata JSON and the
#      augmented eICR XML from S3.
#
# Usage: ./scripts/aws_e2e.sh "<nonstandard test name>"
#

set -euo pipefail

# ── Required tooling ──────────────────────────────────────────────────────────
# gum:      TUI chrome (styled banners, spinners, log levels).
# unbuffer: wraps `aws` in a pseudo-TTY so it line-buffers stdout. Without this
#           the AWS CLI v2 (a PyInstaller bundle that ignores PYTHONUNBUFFERED)
#           block-buffers output when piped and all log lines would arrive in
#           one burst at the end.
command -v gum >/dev/null || {
    echo "This script requires 'gum'. Install with: brew install gum" >&2
    exit 1
}
command -v unbuffer >/dev/null || {
    echo "This script requires 'unbuffer' (from expect). Install with: brew install expect" >&2
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

# Format a single `aws logs tail` line:
#   <timestamp> <YYYY/MM/DD/[$LATEST]<hex>> <message>
# - Dims the timestamp to gray.
# - Drops the repetitive stream-name field (the `YYYY/…/[$LATEST]<hex>` piece).
# - If the message is a JSON object, runs it through `jq -C -c` for compact
#   colored output; otherwise prints it as-is.
# - Lines that don't match the expected shape (e.g. Python tracebacks split
#   across records) are printed raw.
pretty_log_line() {
    local line="$1" ts msg
    if [[ "$line" =~ ^([^[:space:]]+)[[:space:]]+[0-9]{4}/[0-9]{2}/[0-9]{2}/\[[^]]+\][a-f0-9]+[[:space:]](.*)$ ]]; then
        ts="${BASH_REMATCH[1]}"
        msg="${BASH_REMATCH[2]}"
    else
        printf '%s\n' "$line"
        return
    fi
    printf '\033[38;5;245m%s\033[0m ' "$ts"
    if [[ "$msg" == "{"*"}" ]] && printf '%s' "$msg" | jq -e . >/dev/null 2>&1; then
        printf '%s' "$msg" | jq -C -c .
    else
        printf '%s\n' "$msg"
    fi
}

# ── Argument + input validation ───────────────────────────────────────────────

[[ $# -eq 1 ]] || {
    gum style --foreground=red --bold "Usage: $0 \"<nonstandard test name>\""
    exit 1
}
TEST_NAME="$1"

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
FILENAME="$(date +%m-%d-%Y_%H:%M:%S).xml"
TMPDIR="$(mktemp -d)"
trap 'rm -rf "$TMPDIR"' EXIT
TEMPLATED_EICR="$TMPDIR/$FILENAME"

gum style --border=rounded --padding="0 2" --margin="1 0" --foreground=212 --bold \
    "DIBBs Text to Code E2E pipeline test" "" \
    "Test name: $TEST_NAME" \
    "Bucket:    s3://$BUCKET" \
    "Filename:  $FILENAME"

# ── Log-tail phase ────────────────────────────────────────────────────────────
#
# Tail a CloudWatch log group until its `REPORT RequestId:` line appears
# (Lambda's end-of-invocation marker), with:
#
#   • a pinned-bottom braille spinner that animates continuously
#   • log lines appended ABOVE the spinner as they arrive (via \r\033[K to
#     erase the spinner row, print the log line, then redraw the spinner
#     on the now-current bottom row)
#   • `unbuffer` wrapping `aws logs tail` so its output line-buffers
#   • `--color off` so aws emits plain text (the PTY would otherwise trigger
#     color codes that break pretty_log_line's regex)
#
# The loop reads from a FIFO on FD 3 with a 100 ms `read -t` timeout so we
# can animate the spinner while waiting for the next log event. `rc > 128`
# means the read timed out (vs a real EOF, which breaks the loop).
follow_until_report() {
    local log_group="$1" label="$2" start fifo tail_pid line rc
    local -a frames=('⠋' '⠙' '⠹' '⠸' '⠼' '⠴' '⠦' '⠧' '⠇' '⠏')
    local frame_idx=0
    start=$(date +%s)

    section "Watching $label Lambda ($log_group)"

    fifo="$(mktemp -u)"
    mkfifo "$fifo"

    # Redraw the spinner on the current row (\r goes to col 0, \033[K clears
    # to end of line). Advances to the next braille frame on each call.
    draw_spinner() {
        printf '\r\033[K\033[38;5;99m%s\033[0m Tailing %s logs…' \
            "${frames[frame_idx]}" "$label"
        frame_idx=$(( (frame_idx + 1) % ${#frames[@]} ))
    }
    clear_spinner() { printf '\r\033[K'; }

    # Start the tail in the background; read its output from FD 3 so we can
    # use `read -t` on it (needs a persistent FD, not a redirect per-read).
    unbuffer aws logs tail "$log_group" --follow --since 1m --color off >"$fifo" &
    tail_pid=$!
    exec 3<"$fifo"

    draw_spinner

    while :; do
        if IFS= read -r -t 1 -u 3 line; then
            clear_spinner
            pretty_log_line "$line"
            [[ "$line" == *"REPORT RequestId:"* ]] && break
            draw_spinner
        else
            rc=$?
            (( rc > 128 )) || break   # rc > 128 = timeout; anything else = EOF
            draw_spinner              # idle tick — just advance the animation
        fi
    done

    clear_spinner
    exec 3<&-
    kill "$tail_pid" 2>/dev/null || true
    wait "$tail_pid" 2>/dev/null || true
    rm -f "$fifo"

    gum log -l info "$label complete in $(( $(date +%s) - start ))s"
}

wait_for_s3_object() {
    local key="$1" label="$2" timeout="${3:-120}" interval=2 elapsed=0

    while ! aws s3api head-object --bucket "$BUCKET" --key "$key" >/dev/null 2>&1; do
        if (( elapsed >= timeout )); then
            gum log -l error "Timed out waiting for $label at s3://$BUCKET/$key"
            return 1
        fi

        printf '\r\033[K'
        gum spin --spinner=dot --title "Waiting for $label (${elapsed}s/${timeout}s)..." -- sleep "$interval"
        elapsed=$((elapsed + interval))
    done
}

# ── Result fetching ───────────────────────────────────────────────────────────
# Fetch one S3 object and pretty-print it by content type. XML uses `bat` for
# syntax highlighting when available; JSON uses `jq -C` (forced color).
dump_s3() {
    local key="$1" formatter="$2"
    gum style --foreground=51 --bold "── s3://$BUCKET/$key ──"
    local content
    content="$(aws s3 cp "s3://$BUCKET/$key" -)"
    case "$formatter" in
    json)
        jq -C . <<<"$content" 2>/dev/null || echo "$content"
        ;;
    xml)
        local formatted
        formatted="$(xmllint --format - <<<"$content" 2>/dev/null || echo "$content")"
        if command -v bat >/dev/null 2>&1; then
            bat -l xml --style=plain --color=always --paging=never <<<"$formatted"
        else
            echo "$formatted"
        fi
        ;;
    esac
}

# ── Template the eICR ─────────────────────────────────────────────────────────
# Rewrite the first displayName + originalText with $TEST_NAME so the TTC
# pipeline has a unique text candidate to resolve, and stamp fresh UUIDs on
# <id>/<setId> so this eICR looks like a new document to downstream systems.
section "Templating eICR"
TEST_NAME="$TEST_NAME" SOURCE_EICR="$SOURCE_EICR" OUT_PATH="$TEMPLATED_EICR" \
    python3 <<'PYEOF'
import os
import re
import uuid
from xml.sax.saxutils import escape
from xml.sax.saxutils import quoteattr

src = open(os.environ["SOURCE_EICR"]).read()
name = os.environ["TEST_NAME"]

src = re.sub(
    r'displayName="[^"]*"',
    "displayName=" + quoteattr(name),
    src,
    count=1,
)
src = re.sub(
    r"(<originalText[^>]*>)[^<]*(</originalText>)",
    lambda m: m.group(1) + escape(name) + m.group(2),
    src,
    count=1,
)
src = re.sub(
    r'<id root="[0-9a-f-]+"',
    f'<id root="{uuid.uuid4()}"',
    src,
    count=1,
)
src = re.sub(
    r'<setId extension="[0-9a-f-]+"',
    f'<setId extension="{uuid.uuid4()}"',
    src,
    count=1,
)

open(os.environ["OUT_PATH"], "w").write(src)
PYEOF

# ── Fire the pipeline ─────────────────────────────────────────────────────────
# The schematron report must land under ValidationResponseV2/ before the eICR
# under TextToCodeSubmissionV2/, because the eICR put is the S3 event that
# triggers the TTC lambda, which then reads the paired schematron report by
# the same filename.
section "Uploading to S3"
gum spin --spinner=dot --title "Uploading schematron errors…" -- \
    aws s3 cp "$SOURCE_SCHEMATRON" "s3://$BUCKET/ValidationResponseV2/$FILENAME"
gum spin --spinner=dot --title "Uploading templated eICR…" -- \
    aws s3 cp "$TEMPLATED_EICR" "s3://$BUCKET/TextToCodeSubmissionV2/$FILENAME"

# Block until each lambda finishes. TTC writes TTCAugmentationMetadataV2/<name>.json,
# which triggers the augmentation lambda; that's why we watch them in sequence.
follow_until_report "$TTC_LOG" "TTC"
follow_until_report "$AUG_LOG" "Augmentation"

# ── Show the outputs ──────────────────────────────────────────────────────────
section "Fetching results"
wait_for_s3_object "TTCMetadataV2/${FILENAME%.xml}.json" "TTC metadata"
wait_for_s3_object "AugmentationEICRV2/$FILENAME" "augmented eICR"
dump_s3 "TTCMetadataV2/${FILENAME%.xml}.json" json
dump_s3 "AugmentationEICRV2/$FILENAME" xml

gum style --border=double --padding="0 2" --margin="1 0" --foreground=212 \
    "Done — $FILENAME" "" \
    "TTC metadata:    s3://$BUCKET/TTCMetadataV2/${FILENAME%.xml}.json" \
    "Augmented eICR:  s3://$BUCKET/AugmentationEICRV2/$FILENAME" \
    "TTC input:       s3://$BUCKET/TextToCodeSubmissionV2/$FILENAME"
