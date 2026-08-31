#!/usr/bin/env bash
#
# TTC reingestion: replace the LOINC embeddings behind the deployed pipeline.
#
# Halts the TTC lambda (reserved concurrency 0 + event source mapping
# disabled), waits for in-flight work to drain, drops and recreates both
# OpenSearch indices via the index lambda, swaps s3://<bucket>/reingestion/
# into ingestion/ (backing the old set up to ingestion-backup-<ts>/, the
# rollback source), waits for OSIS to repopulate the index to the expected
# document count, then resumes TTC.
#
# Runs in CI under ttc-reingestion-ci-role, invoked by
# .github/workflows/ttc_reingestion.yml. Operator procedure, watchpoints,
# and the recovery table: docs/runbooks/reingest-loinc-embeddings.md.
#
# Usage:
#   ttc-reingestion-embeddings.sh --expected-count <N> [--stability-polls <N>]
#
#   --expected-count   Document count the OpenSearch index must reach (from the embeddings manifest). Required.
#   --stability-polls  Consecutive stable count polls (30 s apart) before the index is considered fully loaded. Default: 3.
#
# Requires: aws, curl, and jq

set -euo pipefail

usage() {
    sed -n '2,22p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
    exit 1
}

command -v aws >/dev/null || { echo "This script requires the AWS CLI." >&2; exit 1; }
command -v curl >/dev/null || { echo "This script requires curl." >&2; exit 1; }
command -v jq >/dev/null || { echo "This script requires jq." >&2; exit 1; }

# ── configuration ─────────────────────────────────────────────────────────────
ESM_POLL_SECONDS=5    ESM_CAP_SECONDS=120
DRAIN_POLL_SECONDS=15 DRAIN_CAP_SECONDS=1200
OSIS_POLL_SECONDS=30  OSIS_CAP_SECONDS=1800
EMBEDDING_DIMENSION=1024  # must match INDEX_MAPPING in packages/index-lambda

REQUIRED_ENV_VARS=(
    AWS_REGION
    TTC_LAMBDA_FUNCTION_NAME
    TTC_INDEX_LAMBDA_FUNCTION_NAME
    TTC_EVENT_SOURCE_MAPPING_UUID
    TTC_INPUT_QUEUE_URL
    TTC_INPUT_DLQ_URL
    TTC_S3_BUCKET
    TTC_INGESTION_PREFIX
    TTC_REINGESTION_PREFIX
    TTC_INGESTION_BACKUP_PREFIX
    TTC_OPENSEARCH_ENDPOINT
    TTC_OPENSEARCH_INDEX
    TTC_ALERT_TOPIC_ARN
)

# ── argument parsing ──────────────────────────────────────────────────────────
EXPECTED_COUNT=""
STABILITY_POLLS=3

while [[ $# -gt 0 ]]; do
    case "$1" in
        --expected-count)  EXPECTED_COUNT="$2"; shift 2 ;;
        --stability-polls) STABILITY_POLLS="$2"; shift 2 ;;
        *) usage ;;
    esac
done

[[ "$EXPECTED_COUNT" =~ ^[1-9][0-9]*$ ]] || usage
[[ "$STABILITY_POLLS" =~ ^[1-9][0-9]*$ ]] || usage

# ── helpers ───────────────────────────────────────────────────────────────────
log() {
    echo "[$(date -u +%H:%M:%S)] $*"
}

die() {
    log "ERROR: $*" >&2
    exit 1
}

queue_attr() {
    local queue_url="$1" attr="$2"
    aws sqs get-queue-attributes --queue-url "$queue_url" \
        --attribute-names "$attr" --query "Attributes.$attr" --output text
}

invoke_index_lambda() {
    local action="$1" out payload
    out="$(mktemp)"
    aws lambda invoke \
        --function-name "$TTC_INDEX_LAMBDA_FUNCTION_NAME" \
        --payload "{\"action\":\"$action\"}" \
        --cli-binary-format raw-in-base64-out \
        "$out" >/dev/null
    payload="$(cat "$out")"
    rm -f "$out"
    if ! jq -e '.statusCode == 200 and .index_recreated == true' <<<"$payload" >/dev/null; then
        die "index lambda '$action' did not confirm recreation: $payload"
    fi
    log "  $action: ok"
}

os_request() {
    local method="$1" path="$2" body="${3:-}"
    local args=(
        -sS --fail-with-body -X "$method"
        "https://${TTC_OPENSEARCH_ENDPOINT}${path}"
        --aws-sigv4 "aws:amz:${AWS_REGION}:es"
        --user "${AWS_ACCESS_KEY_ID}:${AWS_SECRET_ACCESS_KEY}"
        -H "Content-Type: application/json"
    )
    if [[ -n "${AWS_SESSION_TOKEN:-}" ]]; then
        args+=(-H "x-amz-security-token: ${AWS_SESSION_TOKEN}")
    fi
    if [[ -n "$body" ]]; then
        args+=(-d "$body")
    fi
    curl "${args[@]}"
}

wait_for_esm_state() {
    local target="$1" deadline=$(( SECONDS + ESM_CAP_SECONDS )) state
    while :; do
        state="$(aws lambda get-event-source-mapping \
            --uuid "$TTC_EVENT_SOURCE_MAPPING_UUID" \
            --query State --output text)" || state="unknown"
        log "  event source mapping state: $state"
        [[ "$state" == "$target" ]] && return 0
        (( SECONDS < deadline )) || return 1
        sleep "$ESM_POLL_SECONDS"
    done
}

alert_resume_failure() {
    log "CRITICAL: $* — TTC is still halted. Run the manual resume in" >&2
    log "docs/runbooks/reingest-loinc-embeddings.md and page on-call." >&2
    aws sns publish --topic-arn "$TTC_ALERT_TOPIC_ARN" \
        --subject "TTC reingestion: resume failed, TTC is halted" \
        --message "$*. TTC remains halted (event source mapping disabled and/or reserved concurrency 0). Run the manual resume in docs/runbooks/reingest-loinc-embeddings.md." \
        >/dev/null || log "WARNING: SNS publish to TTC_ALERT_TOPIC_ARN also failed." >&2
    exit 1
}

# ── preflight ─────────────────────────────────────────────────────────────────
MISSING_ENV_VARS=()
for var in "${REQUIRED_ENV_VARS[@]}"; do
    [[ -n "${!var:-}" ]] || MISSING_ENV_VARS+=("$var")
done
(( ${#MISSING_ENV_VARS[@]} == 0 )) || die "missing required environment variables: ${MISSING_ENV_VARS[*]}"

FIRST_REINGESTION_KEY="$(aws s3api list-objects-v2 \
    --bucket "$TTC_S3_BUCKET" --prefix "$TTC_REINGESTION_PREFIX" \
    --max-keys 1 --query 'Contents[0].Key' --output text)"
[[ "$FIRST_REINGESTION_KEY" != "None" ]] \
    || die "s3://$TTC_S3_BUCKET/$TTC_REINGESTION_PREFIX is empty — upload the new embeddings first (runbook step 1)"

DLQ_BASELINE="$(queue_attr "$TTC_INPUT_DLQ_URL" ApproximateNumberOfMessages)"
log "Preflight ok: reingestion/ is populated, DLQ baseline is $DLQ_BASELINE message(s)"
log "Target: >= $EXPECTED_COUNT docs, stable for $STABILITY_POLLS consecutive ${OSIS_POLL_SECONDS}s polls"

# ── step 1: halt TTC ──────────────────────────────────────────────────────────
log "Step 1/7 — halting TTC"
# "None" when no reserved concurrency is set; step 6 restores accordingly.
ORIGINAL_CONCURRENCY="$(aws lambda get-function-concurrency \
    --function-name "$TTC_LAMBDA_FUNCTION_NAME" \
    --query ReservedConcurrentExecutions --output text)"
log "  current reserved concurrency: $ORIGINAL_CONCURRENCY"
aws lambda put-function-concurrency \
    --function-name "$TTC_LAMBDA_FUNCTION_NAME" \
    --reserved-concurrent-executions 0 >/dev/null
aws lambda update-event-source-mapping \
    --uuid "$TTC_EVENT_SOURCE_MAPPING_UUID" --no-enabled >/dev/null
wait_for_esm_state Disabled \
    || die "event source mapping did not reach Disabled within ${ESM_CAP_SECONDS}s"

# ── step 2: wait for in-flight TTC drain ──────────────────────────────────────
log "Step 2/7 — waiting for in-flight messages to drain (cap $(( DRAIN_CAP_SECONDS / 60 )) min)"
DRAIN_DEADLINE=$(( SECONDS + DRAIN_CAP_SECONDS ))
while :; do
    INFLIGHT="$(queue_attr "$TTC_INPUT_QUEUE_URL" ApproximateNumberOfMessagesNotVisible)"
    VISIBLE="$(queue_attr "$TTC_INPUT_QUEUE_URL" ApproximateNumberOfMessages)"
    log "  in-flight: $INFLIGHT (visible backlog: $VISIBLE — climbing is expected while halted)"
    [[ "$INFLIGHT" == "0" ]] && break
    (( SECONDS < DRAIN_DEADLINE )) \
        || die "in-flight messages did not drain within $(( DRAIN_CAP_SECONDS / 60 )) min — a lambda is stuck (check /aws/lambda/$TTC_LAMBDA_FUNCTION_NAME). Nothing destructive has happened; re-run once it clears."
    sleep "$DRAIN_POLL_SECONDS"
done

# ── step 3: drop and recreate the indices ─────────────────────────────────────
log "Step 3/7 — dropping and recreating the OpenSearch indices"
invoke_index_lambda clear_index
invoke_index_lambda clear_result_cache

# ── step 4: swap embeddings into ingestion/ ───────────────────────────────────
BACKUP_PREFIX="${TTC_INGESTION_BACKUP_PREFIX}$(date -u +%Y%m%dT%H%M%SZ)/"
log "Step 4/7 — swapping S3 prefixes (rollback source: s3://$TTC_S3_BUCKET/$BACKUP_PREFIX)"
aws s3 sync "s3://$TTC_S3_BUCKET/$TTC_INGESTION_PREFIX" "s3://$TTC_S3_BUCKET/$BACKUP_PREFIX"
aws s3 rm "s3://$TTC_S3_BUCKET/$TTC_INGESTION_PREFIX" --recursive
# These writes fire the S3 -> SQS -> OSIS trigger; ingestion starts here.
aws s3 sync "s3://$TTC_S3_BUCKET/$TTC_REINGESTION_PREFIX" "s3://$TTC_S3_BUCKET/$TTC_INGESTION_PREFIX"

# ── step 5: wait for OSIS ingestion ───────────────────────────────────────────
log "Step 5/7 — waiting for OSIS ingestion (cap $(( OSIS_CAP_SECONDS / 60 )) min)"
OSIS_DEADLINE=$(( SECONDS + OSIS_CAP_SECONDS ))
PREVIOUS_COUNT=-1
STABLE=0
while :; do
    if RESPONSE="$(os_request GET "/${TTC_OPENSEARCH_INDEX}/_count")" \
            && COUNT="$(jq -er '.count' <<<"$RESPONSE")"; then
        (( COUNT <= EXPECTED_COUNT )) \
            || die "document count $COUNT exceeds expected $EXPECTED_COUNT — manifest mismatch, or the sink's document_id key is not unique across the staged files. TTC stays halted; investigate before resuming (runbook step 5)."
        if (( COUNT == PREVIOUS_COUNT )); then
            STABLE=$(( STABLE + 1 ))
        else
            STABLE=0
            PREVIOUS_COUNT=$COUNT
        fi
        log "  document count: $COUNT / $EXPECTED_COUNT (stable polls: $STABLE/$STABILITY_POLLS)"
        # OSIS writes are idempotent (deterministic _id), so anything short of
        # an exact match after stabilizing means documents were dropped.
        (( STABLE >= STABILITY_POLLS && COUNT == EXPECTED_COUNT )) && break
    else
        log "  count poll failed; retrying"
    fi
    (( SECONDS < OSIS_DEADLINE )) \
        || die "index did not reach $EXPECTED_COUNT stable documents within $(( OSIS_CAP_SECONDS / 60 )) min. TTC stays halted; investigate OSIS, then recover per the runbook's step 5 row."
    sleep "$OSIS_POLL_SECONDS"
done

# ── step 6: resume TTC ────────────────────────────────────────────────────────
log "Step 6/7 — resuming TTC"
aws lambda update-event-source-mapping \
    --uuid "$TTC_EVENT_SOURCE_MAPPING_UUID" --enabled >/dev/null \
    || alert_resume_failure "re-enabling the event source mapping failed"
if [[ "$ORIGINAL_CONCURRENCY" == "None" ]]; then
    aws lambda delete-function-concurrency \
        --function-name "$TTC_LAMBDA_FUNCTION_NAME" >/dev/null \
        || alert_resume_failure "removing the reserved concurrency override failed"
else
    aws lambda put-function-concurrency \
        --function-name "$TTC_LAMBDA_FUNCTION_NAME" \
        --reserved-concurrent-executions "$ORIGINAL_CONCURRENCY" >/dev/null \
        || alert_resume_failure "restoring reserved concurrency to $ORIGINAL_CONCURRENCY failed"
fi
wait_for_esm_state Enabled \
    || alert_resume_failure "event source mapping did not reach Enabled within ${ESM_CAP_SECONDS}s"

# ── step 7: smoke test ────────────────────────────────────────────────────────
log "Step 7/7 — smoke test"
KNN_QUERY="$(jq -n --argjson dim "$EMBEDDING_DIMENSION" \
    '{size: 1, query: {knn: {description_vector: {vector: [range($dim) | 0.1], k: 1}}}}')"
SEARCH_RESPONSE="$(os_request POST "/${TTC_OPENSEARCH_INDEX}/_search" "$KNN_QUERY")"
HITS="$(jq -r '.hits.hits | length' <<<"$SEARCH_RESPONSE")"
(( HITS >= 1 )) \
    || die "KNN smoke query returned no hits. TTC is resumed but the index may be unhealthy; investigate before rolling back (runbook step 7)."
log "  KNN smoke query returned $HITS hit(s)"

BACKLOG_BEFORE="$(queue_attr "$TTC_INPUT_QUEUE_URL" ApproximateNumberOfMessages)"
log "  input queue backlog: $BACKLOG_BEFORE; rechecking in 60s to confirm it is draining"
sleep 60
BACKLOG_AFTER="$(queue_attr "$TTC_INPUT_QUEUE_URL" ApproximateNumberOfMessages)"
(( BACKLOG_AFTER == 0 || BACKLOG_AFTER < BACKLOG_BEFORE )) \
    || die "input queue backlog is not decreasing ($BACKLOG_BEFORE -> $BACKLOG_AFTER). TTC is resumed but unhealthy; check /aws/lambda/$TTC_LAMBDA_FUNCTION_NAME. Not rolling back (runbook step 7)."
log "  backlog draining: $BACKLOG_BEFORE -> $BACKLOG_AFTER"

DLQ_CURRENT="$(queue_attr "$TTC_INPUT_DLQ_URL" ApproximateNumberOfMessages)"
(( DLQ_CURRENT <= DLQ_BASELINE )) \
    || die "DLQ depth grew during the run ($DLQ_BASELINE -> $DLQ_CURRENT). See the runbook's DLQ redrive section."
log "  DLQ depth unchanged from baseline ($DLQ_CURRENT)"

log "Reingestion complete: $PREVIOUS_COUNT documents indexed in $(( SECONDS / 60 )) min."
log "Manual post-checks remain (runbook): delete s3://$TTC_S3_BUCKET/$BACKUP_PREFIX once the new embeddings look healthy, and clear s3://$TTC_S3_BUCKET/$TTC_REINGESTION_PREFIX."
