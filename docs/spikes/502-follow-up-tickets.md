# Follow-up tickets for SPIKE #502 — Safely Halt TTC During LOINC Embedding Re-ingestion

Drafts ready to file as GitHub issues. Every ticket links back to the spike:
[docs/spikes/502-reingestion-pause.md](./502-reingestion-pause.md) (SPIKE issue [#502](https://github.com/CDCgov/dibbs-text-to-code/issues/502)).

The pipeline is built and proven in **our environment first** — as a GitHub Actions workflow in this repo against our AWS demo environment — and only then ported to APHL's GitLab (ticket 9). Suggested order: tickets 1–4 are prerequisites for ticket 6 (the GitHub Actions pipeline); ticket 9 comes last. Tickets 5, 7, and 8 are independent.

---

## Ticket 1 — [infra] Add a GitHub-OIDC-trusted IAM role for the TTC re-ingestion workflow

**Summary**

The re-ingestion automation will first be built as a GitHub Actions workflow in this repo, running the AWS CLI against our AWS environment. Every IAM role in `terraform/main.tf` today trusts only `lambda.amazonaws.com` or the OSIS service; the existing deploy workflow assumes a broad Terraform role (`secrets.TERRAFORM_ROLE_ARN`) that is not appropriate for this. Create a new, narrowly-scoped IAM role assumable by GitHub Actions via OIDC federation, granting exactly the actions the pause/re-ingest/resume pipeline needs. (The equivalent GitLab-OIDC role for APHL's environment is part of ticket 9.)

**Acceptance criteria**

- [ ] A new IAM role exists in Terraform whose trust policy uses the GitHub OIDC identity provider (`token.actions.githubusercontent.com`), with conditions restricting assumption to this repository (`CDCgov/dibbs-text-to-code`) and, ideally, to the re-ingestion workflow / protected refs.
- [ ] The role's permission policy grants only:
  - `lambda:UpdateEventSourceMapping`, `lambda:GetEventSourceMapping` on the TTC event source mapping ARN
  - `lambda:PutFunctionConcurrency`, `lambda:GetFunctionConcurrency`, `lambda:DeleteFunctionConcurrency` on the TTC Lambda
  - `lambda:InvokeFunction` on `ttc-index-lambda`
  - `s3:ListBucket` on the bucket; `s3:GetObject`, `s3:PutObject`, `s3:DeleteObject` scoped to `ingestion/*`, `reingestion/*`, and `ingestion-backup-*/*`
  - `es:ESHttpGet` on the OpenSearch domain (for `GET /<index>/_count`)
  - `sqs:GetQueueAttributes` on the TTC input queue and its DLQ
  - `sqs:StartMessageMoveTask`, `sqs:CancelMessageMoveTask`, `sqs:ListMessageMoveTasks` on the TTC DLQ (redrive recovery)
- [ ] No wildcard resources beyond the enumerated S3 prefixes.
- [ ] The role ARN is exposed to the workflow the same way as the existing pattern (e.g. a `REINGESTION_ROLE_ARN` repository secret consumed via `aws-actions/configure-aws-credentials`).

**Reference:** [SPIKE #502 — IAM for GitLab](./502-reingestion-pause.md#iam-for-gitlab)

---

## Ticket 2 — [infra] Switch OSIS pipeline source from 30-day scheduled scan to S3 + SQS notifications

**Summary**

The OSIS pipeline (`ttc-ingestion-pipeline`) currently ingests via a scheduled S3 scan every 30 days (`scan.scheduling.interval = PT720H`). For the re-ingestion pipeline to trigger ingestion by syncing files into `ingestion/`, the source must become event-driven: S3 `ObjectCreated` notifications delivered to a new SQS queue that OSIS consumes.

**Acceptance criteria**

- [ ] A new SQS queue (e.g. `ttc-osis-trigger-queue`) exists in Terraform with a visibility timeout appropriate for OSIS acking (5–10 min per the spike).
- [ ] `ObjectCreated:*` events on `s3://<bucket>/ingestion/*` are delivered to the new queue (either via S3 → EventBridge → SQS, matching the existing TTC/augmentation trigger pattern, or via direct S3 bucket notification — decide and document which).
- [ ] The OSIS pipeline role policy grants `sqs:ReceiveMessage`, `sqs:DeleteMessage`, `sqs:GetQueueAttributes` on the new queue.
- [ ] The OSIS pipeline source block is switched from `scan`/`scheduling` to SQS-notification mode, keeping the existing NDJSON codec.
- [ ] Verified in a non-prod environment: uploading an NDJSON file to `ingestion/` results in the documents appearing in the OpenSearch index within a few minutes, with no scheduled scan required.

**Reference:** [SPIKE #502 — OSIS reconfiguration](./502-reingestion-pause.md#osis-reconfiguration)

---

## Ticket 3 — [infra] Add a `reingestion/` S3 staging prefix and document its lifecycle

**Summary**

The re-ingestion flow stages new embeddings in `s3://<bucket>/reingestion/` before the pipeline syncs them into `ingestion/`. This prefix doesn't exist in the bucket spec today. Add it, grant the necessary access, and document its lifecycle (operator clears it after a successful run; no automatic cleanup).

**Acceptance criteria**

- [ ] The `reingestion/` prefix is added to the bucket spec / Terraform variables alongside the existing prefixes.
- [ ] Write access to `reingestion/` is documented for whoever uploads model-build output (the model team's upload path).
- [ ] The prefix lifecycle is documented: operator uploads before a run, pipeline syncs it to `ingestion/`, operator clears it after success — no S3 lifecycle rule auto-deletes it.
- [ ] The `ingestion-backup-<ts>/` backup-prefix convention used by the pipeline (step 7 of the flow) is documented in the same place.

**Reference:** [SPIKE #502 — Recommended end-to-end flow](./502-reingestion-pause.md#recommended-end-to-end-flow)

---

## Ticket 4 — [iac] Manage ESM `enabled` and TTC reserved concurrency in Terraform with `ignore_changes`

**Summary**

The re-ingestion pipeline toggles the TTC event source mapping and reserved concurrency at runtime via the AWS CLI. Neither attribute is currently declared in Terraform (`aws_lambda_event_source_mapping.ttc_input_sqs` has no `enabled`; `aws_lambda_function.lambda` has no `reserved_concurrent_executions`), so a `terraform apply` during or after a pause could revert or conflict with the pipeline's runtime state. Declare both attributes explicitly and mark them `ignore_changes` so Terraform neither reverts a pause nor drifts.

**Acceptance criteria**

- [ ] `aws_lambda_event_source_mapping.ttc_input_sqs` declares `enabled = true` with `lifecycle { ignore_changes = [enabled] }`.
- [ ] `aws_lambda_function.lambda` declares `reserved_concurrent_executions` (value to match current production intent) with `lifecycle { ignore_changes = [reserved_concurrent_executions] }`.
- [ ] Verified: after manually disabling the ESM and setting concurrency to 0 via the AWS CLI, `terraform plan` shows no diff for either attribute.

**Reference:** [SPIKE #502 — Question 1](./502-reingestion-pause.md#1-how-do-we-halt-sqs-polling)

---

## Ticket 5 — [obs] CloudWatch dashboard and alarms for re-ingestion visibility

**Summary**

During a re-ingestion run, operators have no real-time picture: the CI/CD job reads metrics via API, but there is no dashboard, and the only alarms today are the DLQ visible-message alarms added in #691 (which postdate the spike). Add a dashboard (and alarms where useful) covering the signals an operator watches during a pause/re-ingest/resume cycle.

**Acceptance criteria**

- [ ] A CloudWatch dashboard exists in Terraform covering at minimum:
  - TTC input queue `ApproximateNumberOfMessages` (backlog growth during halt) and `ApproximateNumberOfMessagesNotVisible` (drain signal)
  - TTC Lambda invocations, errors, and throttles
  - TTC DLQ depth
  - OSIS pipeline ingestion metrics (documents written / errors), to the extent OSIS exposes them
- [ ] An alarm fires if the TTC ESM remains disabled (or TTC invocations remain at zero while queue depth grows) beyond the expected halt window (~45 min), catching the "restore step failed" critical failure mode.
- [ ] Existing DLQ alarms from #691 are referenced, not duplicated.
- [ ] The runbook ([docs/runbooks/reingest-loinc-embeddings.md](../runbooks/reingest-loinc-embeddings.md)) is updated to point operators at the dashboard.

**Reference:** [SPIKE #502 — Question 6](./502-reingestion-pause.md#6-observability)

---

## Ticket 6 — [ci/cd] Build a GitHub Actions workflow implementing the pause → re-ingest → resume flow

**Summary**

Build a manually-triggered GitHub Actions workflow in this repo that orchestrates the full re-ingestion against our AWS environment: halt TTC, drain in-flight work, clear the indexes, load new embeddings, verify, and resume. The spike's end-to-end flow table is the spec. This proves the flow end-to-end in our environment before it is ported to APHL's GitLab (ticket 9). Depends on tickets 1 (IAM role), 2 (OSIS event-driven source), 3 (`reingestion/` prefix), and 4 (drift protection).

**Acceptance criteria**

- [ ] Workflow is triggered via `workflow_dispatch` and takes `expected_count` (expected document count) as a required input.
- [ ] Halt: captures current TTC reserved concurrency, sets it to 0, and disables the TTC event source mapping. Augmentation Lambda is untouched.
- [ ] Drain: polls `ApproximateNumberOfMessagesNotVisible` on the TTC input queue until 0, hard-capped at 20 minutes; on timeout the pipeline fails loudly **before** any destructive action.
- [ ] Clear: invokes `ttc-index-lambda` with `{"action":"clear_index"}` then `{"action":"clear_result_cache"}`, asserting `statusCode == 200` and `index_recreated == true` on each response.
- [ ] Load: backs up `ingestion/` to `ingestion-backup-<ts>/`, empties `ingestion/`, then syncs `reingestion/` → `ingestion/`.
- [ ] Verify: polls `GET /<index>/_count` every 30 s until the count is stable for 3 consecutive polls **and** ≥ `expected_count`, hard-capped at 30 minutes.
- [ ] Resume: re-enables the ESM and restores the captured reserved concurrency; if this step fails, the pipeline surfaces a critical, unmissable failure (TTC is still halted).
- [ ] Smoke test: runs a fixed KNN query asserting non-zero hits, and confirms TTC queue depth is decreasing.
- [ ] Each failure mode in the spike's failure-modes table has defined workflow behavior (fail-before-destructive-action, restore-from-backup, or alert-on-call).
- [ ] Steps are written as plain AWS CLI / shell scripts (checked into the repo, called by the workflow) rather than GitHub-Actions-specific constructs wherever practical, so the logic ports to GitLab CI with minimal translation.
- [ ] The workflow is documented in / cross-linked with the operator runbook ([docs/runbooks/reingest-loinc-embeddings.md](../runbooks/reingest-loinc-embeddings.md)).
- [ ] A full re-ingestion run has been executed successfully against our environment using the workflow.

**Reference:** [SPIKE #502 — Recommended end-to-end flow](./502-reingestion-pause.md#recommended-end-to-end-flow) and [Failure modes and rollback](./502-reingestion-pause.md#failure-modes-and-rollback)

---

## Ticket 7 — [ttc] Fail the TTC Lambda when the LOINC index is missing or empty

**Summary**

If a TTC invocation runs against a missing or freshly-cleared index, it currently logs "no match" and acks the SQS message — bad data flows downstream silently. With the ESM disabled during re-ingestion this path should be unreachable, but as defense in depth the Lambda should fail the invocation when the index itself is missing or empty, so any slip-through message lands in the DLQ and can be cleanly redriven after re-ingestion completes.

**Acceptance criteria**

- [ ] When the OpenSearch index does not exist, or exists with a document count of 0, the TTC Lambda raises an error (message returns to the queue and eventually the DLQ) instead of acking with a "no match" result.
- [ ] Legitimate zero-hit queries against a healthy, populated index still behave as today ("no match" is a valid outcome for a term; an empty index is not).
- [ ] The failure emits a distinct, searchable log line (and/or metric) so operators can distinguish "index unavailable" from ordinary processing errors.
- [ ] Unit tests cover: missing index, empty index, and populated-index-with-zero-hits.

**Reference:** [SPIKE #502 — Question 4](./502-reingestion-pause.md#4-how-does-the-index-bootstrap-lambda-fit-into-runtime-re-ingestion) (see `packages/text-to-code-lambda/src/text_to_code_lambda/lambda_function.py:299-338`)

---

## Ticket 8 — [ttc] (Optional) Emit an `_INGEST_COMPLETE` sentinel file as a deterministic ingestion-done signal

**Summary**

The pipeline detects ingestion completion by document-count stabilization, which is heuristic. As a belt-and-suspenders signal, the upload/sync step can write a sentinel `_INGEST_COMPLETE` marker as the final object, giving the completion check a deterministic component alongside the count gate. Nice-to-have; the count-based check is sufficient for v1.

**Acceptance criteria**

- [ ] The sync step (or model-build manifest process) writes `_INGEST_COMPLETE` to `ingestion/` only after all embedding files are uploaded.
- [ ] The sentinel is excluded from OSIS ingestion (prefix/suffix filter) so it doesn't produce a bogus document.
- [ ] The pipeline's completion check optionally consumes the sentinel in addition to (not instead of) the count-stability gate.
- [ ] Behavior is documented in the runbook.

**Reference:** [SPIKE #502 — Question 3](./502-reingestion-pause.md#3-how-do-we-detect-osis-ingestion-completion)

---

## Ticket 9 — [ci/cd] Port the re-ingestion pipeline to APHL's GitLab environment

**Summary**

Once the GitHub Actions workflow (ticket 6) has run successfully end-to-end in our environment, port it to APHL's GitLab CI/CD, where the production automation will live per the spike. This includes the production-side IAM: a GitLab-OIDC-trusted role in APHL's AWS account with the same narrow permission set as ticket 1. Depends on ticket 6.

**Acceptance criteria**

- [ ] An IAM role exists in the APHL/production environment whose trust policy uses the GitLab OIDC issuer, restricted to the specific APHL GitLab project (and protected refs, if supported by their setup), with the same permission set enumerated in ticket 1.
- [ ] A GitLab CI/CD pipeline reproduces the ticket 6 flow (manual trigger, `expected_count` parameter, halt → drain → clear → load → verify → resume → smoke test, same hard caps and failure behavior), reusing the shared shell scripts from ticket 6 where possible.
- [ ] Environment-specific values (queue names, function names, bucket, OpenSearch endpoint, index names) are parameterized, not hardcoded, so the same scripts serve both environments.
- [ ] A full re-ingestion run has been executed successfully via the GitLab pipeline in APHL's environment (or their staging equivalent).
- [ ] The operator runbook ([docs/runbooks/reingest-loinc-embeddings.md](../runbooks/reingest-loinc-embeddings.md)) is updated to reference the GitLab pipeline as the production entry point.

**Reference:** [SPIKE #502 — Goal](./502-reingestion-pause.md#goal) and [IAM for GitLab](./502-reingestion-pause.md#iam-for-gitlab)
