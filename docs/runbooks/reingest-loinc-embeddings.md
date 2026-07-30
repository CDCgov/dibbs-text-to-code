# Runbook — Re-ingest LOINC Embeddings

**Audience:** APHL operators running a model-update re-ingestion via the GitLab CI/CD pipeline.
**Linked design:** [`docs/spikes/502-reingestion-pause.md`](../spikes/502-reingestion-pause.md)
**Estimated wall-clock:** 25–35 min from pipeline start to pipeline success.
**When to use:** After the model team has produced new LOINC embeddings (NDJSON) that need to replace the current index contents.

> [!WARNING]
> Run during an off-hours window when possible. SQS will accumulate a backlog during the halt — that's expected and drained automatically once TTC resumes.

## Pre-flight checklist

Before starting:

- [ ] **Embeddings artifact in hand**, with checksum verified against the model team's manifest.
- [ ] **Expected document count is known** (from the model team's manifest, e.g. `manifest.json` shipped with the embeddings). You'll pass this to the pipeline.
- [ ] **On-call notified** — paste the planned start time in the team channel.
- [ ] **No active model deploys or Terraform applies** in flight against the same environment.
- [ ] **TTC DLQ is empty** (`aws sqs get-queue-attributes --queue-url <ttc-lambda-dlq-url> --attribute-names ApproximateNumberOfMessages`). If not empty, drain or investigate first — the post-run DLQ check in step 7 needs a clean baseline.

## Trigger procedure

### 1. Upload new embeddings

```sh
aws s3 sync ./embeddings/ s3://<bucket>/reingestion/ \
  --exclude "*" --include "*.ndjson" --include "manifest.json"
```

Confirm the upload:

```sh
aws s3 ls s3://<bucket>/reingestion/
```

`reingestion/` is the only prefix the model build writes to; uploading straight to `ingestion/` would be picked up by the next OSIS scan outside a halt window. The IAM scoping for this upload path is documented under [S3 Data Bucket → Access](../../terraform/README.md#access).

### 2. Start the GitLab pipeline

In the GitLab UI: **CI/CD → Pipelines → Run pipeline** for the re-ingestion project. Provide variables:

| Variable             | Example  | Notes                                                           |
| -------------------- | -------- | --------------------------------------------------------------- |
| `EXPECTED_DOC_COUNT` | `123456` | From the embeddings manifest.                                   |
| `ENVIRONMENT`        | `prod`   | Targets the right AWS account / OpenSearch domain.              |
| `STABILITY_POLLS`    | `3`      | Optional; default is 3 (90s of stable count before completion). |

The pipeline runs the 7 steps below.

## What the pipeline does

### Step 1 — Halt TTC

**Expected duration:** < 10 s.

The pipeline:

1. Reads current TTC reserved concurrency and stores it in pipeline state.
2. `aws lambda put-function-concurrency --function-name ttc-lambda --reserved-concurrent-executions 0`.
3. `aws lambda update-event-source-mapping --uuid <esm-uuid> --no-enabled`.

**Watch:** `aws lambda get-event-source-mapping --uuid <esm-uuid>` shows `State: Disabling → Disabled`.
**Augmentation is NOT halted** — it doesn't query OpenSearch and is safe to keep running.
**If this hangs:** the AWS API call is fast; a hang means an IAM/permissions problem. Check the GitLab role can call `lambda:UpdateEventSourceMapping`.

### Step 2 — Wait for in-flight TTC drain

**Expected duration:** up to 15 min (TTC Lambda timeout). Hard cap 20 min.

The pipeline polls every 15 s:

```sh
aws sqs get-queue-attributes --queue-url <ttc-lambda-queue-url> \
  --attribute-names ApproximateNumberOfMessagesNotVisible
```

Drain is complete when this returns `0`.

**Watch:** `ApproximateNumberOfMessages` (visible) will keep climbing as the eICR pipeline continues to identify candidates for TTC. Don't be alarmed.
**If this exceeds 20 min:** pipeline fails before any destructive action. A long-running Lambda is stuck — check `/aws/lambda/ttc-lambda` log group for the affected eICR. After it finishes (or you manually kill it), re-run the pipeline.

### Step 3 — Drop and recreate the index

**Expected duration:** < 60 s.

```sh
aws lambda invoke \
  --function-name ttc-index-lambda \
  --payload '{"action":"clear_index"}' \
  --cli-binary-format raw-in-base64-out \
  /tmp/index-out.json
```

Then,

```sh
aws lambda invoke \
  --function-name ttc-index-lambda \
  --payload '{"action":"clear_result_cache"}' \
  --cli-binary-format raw-in-base64-out \
  /tmp/index-out.json
```

For each command, the pipeline asserts the response payload contains:

```json
{ "statusCode": 200, "index_recreated": true }
```

**Watch:** OpenSearch console → Indices → `ttc-index` should show 0 documents immediately after.
**If this fails:** the index Lambda log group `/aws/lambda/ttc-index-lambda` will have the error. Common cause: VPC connectivity. Pipeline halts here; embeddings haven't been touched, so just rollback (step "Manual rollback" below).

### Step 4 — Swap embeddings into ingestion/

**Expected duration:** depends on file size, typically 30 s – 2 min.

```sh
# Backup current ingestion/ contents
aws s3 sync s3://<bucket>/ingestion/ s3://<bucket>/ingestion-backup-$(date -u +%Y%m%dT%H%M%SZ)/

# Empty ingestion/
aws s3 rm s3://<bucket>/ingestion/ --recursive

# Promote reingestion/ → ingestion/
aws s3 sync s3://<bucket>/reingestion/ s3://<bucket>/ingestion/
```

The S3 ObjectCreated events on `ingestion/*` feed the OSIS SQS-driven source, kicking off ingestion automatically. The sync is a copy — `reingestion/` still holds the new embeddings afterwards, and you clear it in the post-checks below. One `ingestion-backup-<ts>/` prefix is created per run; nothing deletes it automatically. See [S3 Data Bucket](../../terraform/README.md#s3-data-bucket-s3tf) for the full prefix layout.

**Watch:** `aws s3 ls s3://<bucket>/ingestion/` shows the new file set; `aws s3 ls s3://<bucket>/ingestion-backup-<ts>/` confirms backup.
**If this fails:** the backup copy is intact. Re-attempt the sync, or run the manual rollback.

### Step 5 — Wait for OSIS ingestion to finish

**Expected duration:** 10–15 min. Hard cap 30 min.

The pipeline polls every 30 s:

```sh
curl -s -X GET "https://<opensearch-endpoint>/<index>/_count" \
  --aws-sigv4 "aws:amz:<region>:es"
```

Completion criteria (both must hold):

- Count is stable across `STABILITY_POLLS` consecutive polls (default 3 → 90 s).
- Count ≥ `EXPECTED_DOC_COUNT`.

**Watch:**

- OpenSearch console → Indices → `ttc-index` doc count climbing.
- OSIS pipeline metrics: `aws osis get-pipeline --pipeline-name ttc-ingestion-pipeline` → look for `recordsIn` / `recordsOut`.
- OSIS audit log group: `/aws/vendedlogs/OpenSearchIngestion/ttc-ingestion-pipeline/audit`.

**If the count stalls below expected:** check OSIS log group for parse errors. Common cause: malformed NDJSON. Fix the file in `reingestion/`, re-run from step 6 (the index is already empty).
**If the count exceeds expected:** indicates duplicate ingestion or a manifest mismatch. Pause and investigate before resuming TTC.

### Step 6 — Resume TTC

**Expected duration:** < 10 s.

1. `aws lambda update-event-source-mapping --uuid <esm-uuid> --enabled`.
2. `aws lambda put-function-concurrency --function-name ttc-lambda --reserved-concurrent-executions <captured-value>`.
   - If the captured value was "no reserved concurrency set", call `aws lambda delete-function-concurrency` instead.

**Watch:** `aws lambda get-event-source-mapping --uuid <esm-uuid>` shows `State: Enabling → Enabled`.
**If this fails:** **critical.** TTC stays halted. Run the two CLI commands manually and page on-call.

### Step 7 — Smoke test and verify

**Expected duration:** < 1 min.

The pipeline:

1. Runs a fixed KNN query against `ttc-index` and asserts ≥ 1 hit.
2. Polls `ApproximateNumberOfMessages` on `ttc-lambda-queue` for 60 s and asserts the backlog is decreasing.
3. Confirms `ApproximateNumberOfMessages` on `ttc-lambda-dlq` is unchanged from the pre-flight baseline.

**If smoke fails:** TTC is running but processing is unhealthy. Check `/aws/lambda/ttc-lambda` for exceptions. Do not roll back the embeddings until you've identified the cause — the embeddings may be fine and the issue elsewhere.

## Estimated total wall-clock

| Phase                 | Time                      |
| --------------------- | ------------------------- |
| Halt + drain          | 0–20 min (typically 5–10) |
| Drop + recreate index | < 1 min                   |
| S3 swap               | < 2 min                   |
| OSIS ingest           | 10–15 min                 |
| Resume + verify       | < 2 min                   |
| **Total**             | **~25–35 min**            |

## Manual rollback

Use this if step 3, 4, or 5 fails _before_ TTC has been resumed.

```sh
# 1. Restore the previous embeddings
aws s3 rm s3://<bucket>/ingestion/ --recursive
aws s3 sync s3://<bucket>/ingestion-backup-<ts>/ s3://<bucket>/ingestion/

# 2. Recreate both indices (Vector Search and Result Cache) from the backup contents (OSIS will reload them)
aws lambda invoke \
  --function-name ttc-index-lambda \
  --payload '{"action":"clear_index"}' \
  --cli-binary-format raw-in-base64-out \
  /tmp/index-out.json

aws lambda invoke \
  --function-name ttc-index-lambda \
  --payload '{"action":"clear_result_cache"}' \
  --cli-binary-format raw-in-base64-out \
  /tmp/index-out.json

# 3. Wait for OSIS to repopulate (poll _count as in step 7)

# 4. Resume TTC (same as step 8)
aws lambda update-event-source-mapping --uuid <esm-uuid> --enabled
aws lambda put-function-concurrency \
  --function-name ttc-lambda \
  --reserved-concurrent-executions <captured-value>
```

## Recovery — pipeline failed partway

| Failed step | Recovery                                                                                                                   |
| ----------- | -------------------------------------------------------------------------------------------------------------------------- |
| Step 1      | No state changed. Re-run pipeline.                                                                                         |
| Step 2      | Halt is in place; nothing destructive yet. Wait for the stuck Lambda to finish, then re-run pipeline.                      |
| Step 3      | Index drop failed. Rollback (above) is a no-op (index hasn't been emptied) — just resume TTC manually and re-run pipeline. |
| Step 4      | Sync partially complete. Run manual rollback to restore from `ingestion-backup-<ts>/`, then re-run pipeline.               |
| Step 5      | OSIS not catching up. Investigate first; rollback is the same as step 6.                                                   |
| Step 6      | **TTC is stuck halted.** Run the two AWS CLI commands manually and page on-call.                                           |
| Step 7      | Smoke test failed but TTC is running. Investigate logs; do not auto-rollback.                                              |

### Redriving DLQ messages

If TTC messages landed in the DLQ during the run (shouldn't happen with the ESM-disable approach, but possible during operator error):

```sh
aws sqs start-message-move-task \
  --source-arn arn:aws:sqs:<region>:<account>:ttc-lambda-dlq \
  --destination-arn arn:aws:sqs:<region>:<account>:ttc-lambda-queue
```

Monitor:

```sh
aws sqs list-message-move-tasks \
  --source-arn arn:aws:sqs:<region>:<account>:ttc-lambda-dlq
```

## Post-checks (next 1 hour)

After the pipeline succeeds:

- [ ] `ApproximateNumberOfMessages` on `ttc-lambda-queue` returns to its normal baseline within ~1 hour (depends on backlog size and Lambda concurrency).
- [ ] `ApproximateNumberOfMessages` on `ttc-lambda-dlq` stays at its pre-flight baseline.
- [ ] Spot-check 3–5 augmented eICR documents in `s3://<bucket>/AugmentationEICRV2/` from after the swap; confirm `<translation>` elements look reasonable.
- [ ] CloudWatch alarms: no firing alarms on TTC error rate, throttles, or OpenSearch domain health.
- [ ] Delete the `ingestion-backup-<ts>/` prefix once you've confirmed the new embeddings are healthy (recommend keeping for at least 24 h).

```sh
aws s3 rm s3://<bucket>/ingestion-backup-<ts>/ --recursive
```

- [ ] Clear the staging prefix — `reingestion/` still holds a copy of the embeddings the pipeline promoted, and nothing expires it automatically. Leave it populated only if you expect to re-run the same build.

```sh
aws s3 rm s3://<bucket>/reingestion/ --recursive
```

> [!NOTE]
> There are no S3 lifecycle rules on this bucket — both cleanups above are manual. A stale `reingestion/` isn't read outside a run, but it makes it ambiguous which build is live, and a later run started before the next upload would silently promote the old files.
