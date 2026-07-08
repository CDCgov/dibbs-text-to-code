# Lambda performance tuning levers (not yet applied)

A 2026-07 performance audit fixed the code-level hot spots (node-relative XPath
extraction, batched cache lookups and embeddings, Saxon processor/stylesheet
caching, removal of the S3 pre-flight HEAD, HF offline mode in the TTC image).
Two infrastructure levers were identified but deliberately **not** changed,
because they alter cost or delivery behavior. They are recorded here so the
trade-offs don't have to be rediscovered.

## Provisioned concurrency on the TTC Lambda

Every new concurrent execution of `ttc-lambda` cold-starts torch plus two
SentenceTransformer models (multi-second init). There is currently no
`provisioned_concurrency_config` or `reserved_concurrent_executions` in
`terraform/`.

- **When to apply:** if eICR volume becomes bursty or latency-sensitive enough
  that scale-out cold starts show up in end-to-end delivery times.
- **Cost:** provisioned concurrency bills for idle warm containers; at current
  steady, low-volume SQS traffic the cold-start rate is low and the spend is
  likely not justified.

## SQS batch size > 1

Both event source mappings use `batch_size = 1` (`terraform/main.tf`). Raising
it would let one warm container process several eICRs per poll, amortizing
per-invocation overhead.

- **Safety:** partial-batch-failure is already wired
  (`function_response_types = ["ReportBatchItemFailures"]` and
  `batchItemFailures` in both handlers), so a failing record would not force
  retries of its batch-mates.
- **Why it's 1 today:** each record is ML-heavy and isolated; `batch_size = 1`
  keeps per-record timeout budgets simple (one record gets the Lambda's full
  900s/300s). Raising it requires checking that the timeout still covers the
  worst-case batch.
