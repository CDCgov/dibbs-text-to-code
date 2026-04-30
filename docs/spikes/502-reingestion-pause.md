# SPIKE #502 — Safely Halt TTC During LOINC Embedding Re-ingestion

**Status:** Draft for review
**Issue:** [#502](https://github.com/CDCgov/dibbs-text-to-code/issues/502)
**Time-box:** 2–3 engineering days
**Owner:** Nick Clyde

## Background

Each time a new fine-tuned model is deployed, the LOINC vector embeddings stored in OpenSearch must be regenerated. The current manual process is:

1. Fine-tuning produces new vector embeddings.
2. Embeddings are uploaded to `s3://<bucket>/ingestion/`.
3. The index Lambda (`ttc-index-lambda`) drops and recreates the OpenSearch index.
4. The OpenSearch Ingestion (OSIS) pipeline `ttc-ingestion-pipeline` bulk-loads the new embeddings (~10–15 min).

In production, the TTC Lambda keeps polling SQS during steps 3–4 and queries a missing or partially populated index, producing degraded code mappings for any eICR received in that window. The TTC Lambda's current behaviour is to log "no match" and ack the SQS message as success — bad data flows downstream silently.

## Goal

A concrete mechanism for safely pausing TTC processing during re-ingestion, automated end-to-end so the production pause is as short as possible. APHL has confirmed the automation will live in their GitLab CI/CD with AWS CLI access. SQS is allowed to back up during the halt — that is expected behaviour.

## Recommended end-to-end flow

The operator drives a single GitLab pipeline. The pipeline is started **manually** for v1 (auto-trigger via S3 events is a future enhancement).

| Step | Actor | Action | Verification |
|---|---|---|---|
| 1 | Operator | Upload new embeddings (NDJSON) to `s3://<bucket>/reingestion/`. | `aws s3 ls` or the AWS console shows the new files. |
| 2 | Operator | Manually start the GitLab pipeline, supplying the expected document count as an input parameter (alternatively, we can hardcode this, but given LOINC updates, we probably want it to be configurable at trigger time). | Pipeline run begins. |
| 3 | CI/CD | Capture current TTC reserved concurrency. Set TTC reserved concurrency to `0` **and** disable the TTC event source mapping. Augmentation is left running. | `get-function-concurrency` returns 0; `get-event-source-mapping` returns `State: Disabled`. |
| 4 | CI/CD | Poll `ApproximateNumberOfMessagesNotVisible` on `ttc-lambda-queue` until it reaches 0. **Hard cap at 20 min** (15-min Lambda timeout + 5-min slop); fail loudly if exceeded. | CloudWatch metric / `get-queue-attributes`. |
| 5 | CI/CD | Invoke `ttc-index-lambda` with payload `{"action":"clear_index"}`. | `statusCode == 200` and `index_recreated == true` in response payload. |
| 6 | CI/CD | Empty `s3://<bucket>/ingestion/` (potentially taking a backup copy to `ingestion-backup-<ts>/`), then `aws s3 sync s3://<bucket>/reingestion/ s3://<bucket>/ingestion/`. The S3 ObjectCreated events feed the new SQS-driven OSIS source — see [OSIS reconfig](#osis-reconfiguration) below. | `aws s3 ls` shows new file set in `ingestion/`. |
| 7 | CI/CD | Poll OpenSearch `GET /<index>/_count` every 30 s until: count is **stable for N consecutive polls** (recommend N = 3) **and** `≥ expected_count` supplied in step 2. Hard cap at 30 min. | `_count` API. |
| 8 | CI/CD | Re-enable the TTC event source mapping; restore reserved concurrency to the value captured in step 3. | `State: Enabled`; concurrency restored. |
| 9 | CI/CD | Smoke-test: run a fixed KNN query and assert non-zero hits; observe `ApproximateNumberOfMessages` on `ttc-lambda-queue` decreasing. | KNN result; queue depth trend. |

Estimated total wall-clock: **~25–35 min** (drain ≤ 20 min, ingest 10–15 min, restore < 1 min).

## Key technical considerations

These shape the design and correct two assumptions we originally had in the SPIKE.

### Reserved-concurrency-0 does NOT kill in-flight Lambdas

This is the most important correction. Per AWS Lambda docs:

> "To intentionally throttle a function, set its reserved concurrency to 0. This stops your function from processing any **events** until you remove the limit."

It throttles new invocations only; running invocations complete normally. The CI/CD job must therefore **wait for in-flight to drain** rather than assume cancellation. Worst-case drain is the TTC Lambda's `timeout = 900s` (`terraform/main.tf:416-439`) — i.e. 15 min.

### Augmentation Lambda is independent of OpenSearch

`packages/augmentation-lambda/src/augmentation_lambda/lambda_function.py` does not import `opensearch` and does not query the index. It only reads TTC output and original eICR XML from S3, augments in-memory, and writes back. **It does not need to be halted** during re-ingestion. The original ask's "poll until all TTC and Augmentation lambdas complete" can be simplified to TTC only.

### Concurrency-0 has a DLQ-pressure risk; ESM-disable doesn't

With reserved concurrency at 0 and the ESM (event source mapping) still enabled, the ESM keeps polling SQS. Each poll attempt invokes the Lambda, gets throttled, and returns the message to the queue. With `max_receive_count = 3` (`terraform/main.tf:761-787`), messages can land in the DLQ (dead-letter queue) if the halt outlasts 3x the visibility timeout. Visibility timeout is 5400s (90 min) — 3× = 4.5 h. A correctly-bounded halt (~25 min) won't hit that, but the safety margin is small.

**Disabling the ESM** stops polling cleanly with zero DLQ pressure. This design doc recommends doing **both**: disable ESM (primary halt) and concurrency=0 (defence in depth, and it satisfies APHL's stated preference).

### Index Lambda already supports atomic drop+recreate

`packages/index-lambda/src/index_lambda/lambda_function.py:36-138` accepts `{"action": "clear_index"}` which deletes-then-creates the index in one invocation. No new code needed.

### OSIS today uses 30-day scheduled scans

`terraform/main.tf:547-595` (line 565: `scan.scheduling.interval = "PT720H"`). For step 6 to actually trigger ingestion, the source mode must change to **S3 + SQS notifications**. See [OSIS reconfiguration](#osis-reconfiguration).

### No CI/CD-assumable IAM role exists today

All roles in `terraform/main.tf` trust `lambda.amazonaws.com` or the OSIS service. A new GitLab-OIDC-trusted role is required. See [IAM for GitLab](#iam-for-gitlab).

### No CloudWatch alarms exist today

No `aws_cloudwatch_metric_alarm` or `aws_cloudwatch_dashboard` resources exist in `terraform/`. The CI/CD job will read raw metrics via the API; operators have nothing to watch in real time without new dashboards.

## Answers to the six issue questions

### 1. How do we halt SQS polling?

**Recommendation: B + D combined — disable the event source mapping (primary) plus set reserved concurrency to 0 (secondary).**

The CI/CD job runs the AWS CLI directly (no Terraform run per pause/resume). To prevent IaC drift, the Terraform definitions of the ESM and the Lambda's `reserved_concurrent_executions` must use `lifecycle { ignore_changes = [enabled, reserved_concurrent_executions] }`. This is captured in [Follow-up tickets](#follow-up-tickets).

| Option | Verdict | Rationale |
|---|---|---|
| A. Toggle `enabled` via Terraform | **Rejected** | Slow per pause/resume; requires Terraform credentials in CI/CD. |
| B. `aws lambda update-event-source-mapping --no-enabled` | **Recommended (primary)** | Fast, clean stop of polling; in-flight drains naturally. Drift mitigated by `ignore_changes`. |
| C. Feature-flag env var read at Lambda runtime | **Rejected** | Adds runtime complexity; messages still get invoked, hit OS, and must be NACKed; visibility-timeout interactions are messy. |
| D. Reserved concurrency = 0 | **Recommended (secondary)** | APHL's stated preference. Used as defence-in-depth alongside (B). Note the in-flight-not-killed correction above. |

### 2. How do we drain in-flight messages before dropping the index?

Watch `ApproximateNumberOfMessagesNotVisible` on `ttc-lambda-queue`. Drain is complete when this value is 0. Worst-case duration is the Lambda timeout, **15 min** (900s — `terraform/main.tf:416-439`). The CI/CD job uses a hard cap of 20 min; if exceeded, the pipeline fails loudly without proceeding to the index drop.

`ApproximateNumberOfMessages` (visible messages) will keep growing during the halt and is *not* a drain signal — it represents the backlog APHL has acknowledged is acceptable.

### 3. How do we detect OSIS ingestion completion?

**Recommendation: poll `GET /<index>/_count` for stability + minimum-count gate.**

Specifics:
- Poll every 30s.
- Require count to be stable across N consecutive polls (recommend N = 3 → 90s of stability).
- Require count ≥ `expected_count`, supplied as a CI/CD parameter by the operator (read from a manifest produced by the model build).
- Hard cap at 30 min.

Alternatives considered:
- **Shorten OSIS scan interval temporarily** — fragile, requires Terraform run to revert; obsolete after the OSIS reconfig below.
- **CloudWatch Logs pattern matching on `/aws/osis/...`** — OSIS does not emit a deterministic completion marker.
- **Sentinel "done" file via S3 event** — useful as a belt-and-suspenders signal; captured as an optional follow-up ticket.
- **Pure manual verification** — not compatible with the automation goal.

### 4. How does the index bootstrap Lambda fit into runtime re-ingestion?

The CI/CD job invokes it directly:

```sh
aws lambda invoke \
  --function-name ttc-index-lambda \
  --payload '{"action":"clear_index"}' \
  --cli-binary-format raw-in-base64-out \
  /tmp/index-out.json
```

Then asserts the response payload contains `statusCode == 200` and `index_recreated == true`. The Lambda's existing `clear_index` branch in `packages/index-lambda/src/index_lambda/lambda_function.py:61-79` is a single delete-then-create, so no race window between drop and recreate.

A TTC query that slips through between drop and first-document-load returns zero hits. Today the Lambda treats zero hits as a graceful "no match" and acks the SQS message (`packages/text-to-code-lambda/src/text_to_code_lambda/lambda_function.py:299-338`) — bad data passes silently. With the ESM disabled (recommendation 1), this path is unreachable. As an additional safeguard, follow-up ticket 7 proposes failing the invocation when the index is empty/missing so any slip-through DLQs instead of silently degrading.

### 5. What does the operator runbook look like?

See [`docs/runbooks/reingest-loinc-embeddings.md`](../runbooks/reingest-loinc-embeddings.md). It is structured as the operator-facing companion to the 9-step flow above, with per-step durations, watchpoints, failure responses, and a rollback path.

### 6. Observability

Today there are zero alarms or dashboards. The CI/CD job will function without them (it reads metrics via API), but operators have no real-time picture during the run. It may be worth considering a follow-up ticket for a dashboard or alarms.

## OSIS reconfiguration

The current pipeline (`terraform/main.tf:547-595`) configures the s3 source as a scheduled scan:

```yaml
source:
  s3:
    scan:
      buckets:
        - bucket:
            name: ${bucket}
            filter:
              include_prefix: ["${ingestion_prefix}"]
      scheduling:
        interval: PT720H        # ← every 30 days
```

Switch the source mode to **SQS-notification-driven**:

```yaml
source:
  s3:
    notification_type: sqs
    notification_source: eventbridge   # via S3 → EventBridge → SQS, or
                                       # directly via S3 bucket notification → SQS
    sqs:
      queue_url: <new-osis-trigger-queue-url>
    codec:
      ndjson: {}                       # existing codec
```

New AWS resources required (Terraform):

- A new SQS queue, e.g. `ttc-osis-trigger-queue`, with appropriate visibility timeout for OSIS to ack (recommend 5–10 min).
- An S3 bucket notification on `s3://<bucket>/ingestion/*` for `s3:ObjectCreated:*` events, targeting the new queue.
- Updated OSIS pipeline-role policy granting `sqs:ReceiveMessage`, `sqs:DeleteMessage`, `sqs:GetQueueAttributes` on the new queue.

This is captured in [Follow-up tickets](#follow-up-tickets) (ticket 2).

## IAM for GitLab

A new IAM role trusted by GitLab CI/CD via OIDC federation. Scoped policy must include:

- `lambda:UpdateEventSourceMapping` and `lambda:GetEventSourceMapping` on the TTC ESM ARN
- `lambda:PutFunctionConcurrency`, `lambda:GetFunctionConcurrency`, `lambda:DeleteFunctionConcurrency` on `ttc-lambda`
- `lambda:InvokeFunction` on `ttc-index-lambda`
- `s3:ListBucket` on the bucket; `s3:GetObject`, `s3:PutObject`, `s3:DeleteObject`, `s3:CopyObject` scoped to `ingestion/*`, `reingestion/*`, and `ingestion-backup-*/*`
- `es:ESHttpGet` on the OpenSearch domain (for `/<index>/_count`)
- `sqs:GetQueueAttributes` on `ttc-lambda-queue` and `ttc-lambda-dlq`
- `sqs:StartMessageMoveTask`, `sqs:CancelMessageMoveTask`, `sqs:ListMessageMoveTasks` on `ttc-lambda-dlq` (for redrive recovery)
- `cloudwatch:GetMetricData` (optional — only if reading drain metrics through CloudWatch rather than `get-queue-attributes`)

The trust policy uses the GitLab OIDC issuer. Captured in [Follow-up tickets](#follow-up-tickets) (ticket 1).

## Failure modes and rollback

| Failure | Detection | Response |
|---|---|---|
| Drain doesn't complete in 20 min | Step 4 timeout | Pipeline fails before any destructive action. Investigate why a Lambda invocation is running long; manually re-run pipeline once unstuck. No rollback needed. |
| Index Lambda invocation fails | Step 5 non-200 | Pipeline fails. Re-enable ESM and restore concurrency immediately as a rollback. New embeddings still in `reingestion/`; no data loss. |
| OSIS doesn't pick up new files | Step 7 count never rises | Check OSIS pipeline status (`get-pipeline`). If broken: copy `ingestion-backup-<ts>/` back to `ingestion/`, re-enable ESM, restore concurrency. Old embeddings are restored once OSIS catches up. |
| Document count never reaches expected | Step 7 timeout | Same as above — restore from backup. |
| Restore-concurrency / re-enable ESM step fails | Step 8 error | **Critical.** TTC stays halted. Manually run the two AWS CLI commands; alert on-call. |
| TTC messages DLQ during halt despite ESM disable | DLQ alarm fires | Use `aws sqs start-message-move-task` to redrive once index is repopulated. |
| Slip-through eICR processed against partial index | Smoke KNN returns degraded results | Identify affected eICRs (timestamp range from CloudWatch logs), reprocess them by re-publishing to the input prefix. Mitigated by ESM-disable (recommendation 1) and follow-up ticket 7. |

## Out of scope

- **Model fine-tuning** — handled separately by the model team (AKA Brandon); this pipeline starts from an embeddings file.
- **Halting the Augmentation Lambda** — it doesn't query OpenSearch and is unaffected by index swap (verified above).
- **Fully automated triggering** of the GitLab pipeline from S3 events — captured as a future enhancement, not v1.
- **Re-architecting OSIS more broadly** — this SPIKE only proposes the source-mode change required to make step 6 work.

## Follow-up tickets

These are proposed; create as GitHub issues when ready.

1. **[infra] Add GitLab-OIDC-trusted IAM role for TTC re-ingestion CI/CD.** Trust policy + scoped policy enumerated in [IAM for GitLab](#iam-for-gitlab).
2. **[infra] Switch OSIS pipeline source from scheduled scan to S3-SQS.** New SQS trigger queue, S3 ObjectCreated notification on `ingestion/`, OSIS pipeline-role policy update, OSIS source-mode block update.
3. **[infra] Add a `reingestion/` S3 prefix to the bucket spec; document its lifecycle.** No auto-cleanup; operator clears after success.
4. **[infra/iac] Add `enabled = true` and `reserved_concurrent_executions` to the Terraform definitions for the TTC ESM and `ttc-lambda`, with `lifecycle { ignore_changes = [...] }` for both.** Prevents the CI/CD job's runtime toggles from drifting on the next `terraform apply`.
5. **[obs] CloudWatch alarms + dashboard.** Coverage list in [Question 6](#6-observability).
6. **[ci/cd] Build the GitLab pipeline implementing the 9-step flow.** Lives in APHL's GitLab; this SPIKE is the spec.
7. **[ttc] Make the TTC Lambda fail when `_count` of the index is 0 / index missing.** Today silent degradation in `packages/text-to-code-lambda/src/text_to_code_lambda/lambda_function.py:299-338`. Failing fast lets DLQ-redrive cleanly recover any slip-through traffic.
8. **[ttc] Optional: emit a sentinel `_INGEST_COMPLETE` marker file** as the last upload of step 6 so the count-stabilization check has a deterministic signal alongside the document-count check.

## Code/infra references

- TTC Lambda + timeout: `terraform/main.tf:416-439`
- TTC queue + DLQ: `terraform/main.tf:761-787`
- TTC event source mapping: `terraform/main.tf:819-823`
- Augmentation S3-EventBridge → SQS → Lambda: `terraform/main.tf:700-730`
- OSIS pipeline (current PT720H scan): `terraform/main.tf:547-595`
- Index Lambda invocation pattern: `terraform/main.tf:605-613`
- TTC handler & OS query failure mode: `packages/text-to-code-lambda/src/text_to_code_lambda/lambda_function.py:47-85, 299-338`
- Index Lambda `clear_index` action: `packages/index-lambda/src/index_lambda/lambda_function.py:36-138`
- Augmentation Lambda (no OpenSearch): `packages/augmentation-lambda/src/augmentation_lambda/lambda_function.py`
