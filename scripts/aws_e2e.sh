#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BUCKET="dibbs-text-to-code"
SOURCE_EICR="$SCRIPT_DIR/test_eicr.xml"
SOURCE_SCHEMATRON="$SCRIPT_DIR/test_schematron_errors.xml"
TTC_LOG="/aws/lambda/ttc-lambda"
AUG_LOG="/aws/lambda/ttc-augmentation-lambda"
AWS_REGION="us-east-2"

[[ $# -eq 1 ]] || {
    echo "Usage: $0 \"<nonstandard test name>\"" >&2
    exit 1
}
TEST_NAME="$1"

[[ -f "$SOURCE_EICR" ]] || {
    echo "Missing $SOURCE_EICR" >&2
    exit 1
}
[[ -f "$SOURCE_SCHEMATRON" ]] || {
    echo "Missing $SOURCE_SCHEMATRON" >&2
    exit 1
}

follow_until_report() {
    local log_group="$1" label="$2"
    local fifo
    fifo="$(mktemp -u)"
    mkfifo "$fifo"

    echo ">>> Following $label logs ($log_group)..." >&2

    PYTHONUNBUFFERED=1 aws logs tail "$log_group" --follow --since 1m >"$fifo" &
    local tail_pid=$!

    awk '{ print; fflush() } /REPORT RequestId:/ { exit }' <"$fifo"

    kill "$tail_pid" 2>/dev/null || true
    wait "$tail_pid" 2>/dev/null || true
    rm -f "$fifo"
}

dump_s3() {
    local key="$1" formatter="$2"
    echo "===== s3://$BUCKET/$key =====" >&2
    local content
    content="$(aws s3 cp "s3://$BUCKET/$key" -)"
    case "$formatter" in
    json) jq . <<<"$content" 2>/dev/null || echo "$content" ;;
    xml) xmllint --format - <<<"$content" 2>/dev/null || echo "$content" ;;
    esac
}

FILENAME="$(date +%m-%d-%Y_%H%M%S).xml"
TMPDIR="$(mktemp -d)"
trap 'rm -rf "$TMPDIR"' EXIT
TEMPLATED_EICR="$TMPDIR/$FILENAME"

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

aws s3 cp "$SOURCE_SCHEMATRON" "s3://$BUCKET/ValidationResponseV2/$FILENAME"
aws s3 cp "$TEMPLATED_EICR" "s3://$BUCKET/TextToCodeSubmissionV2/$FILENAME"

follow_until_report "$TTC_LOG" "TTC"
follow_until_report "$AUG_LOG" "Augmentation"

dump_s3 "TTCMetadataV2/${FILENAME%.xml}.json" json
dump_s3 "AugmentationEICRV2/$FILENAME" xml

echo "Done. Filename: $FILENAME" >&2
