# scripts/

## `aws_e2e.sh`

End-to-end smoke test for the deployed DIBBs TTC pipeline.

Given a "nonstandard test name" (e.g. `"Zucchini IgG"`), the script:

1. Templates `test_eicr.xml` with that name and fresh UUIDs for `<id>` and `<setId>`.
2. Runs real Schematron validation against the templated eICR (via the in-repo `validation` package) and uploads that report to `s3://dibbs-text-to-code/ValidationResponseV2/`, then the templated eICR to `s3://dibbs-text-to-code/TextToCodeSubmissionV2/` — the eICR upload fires the TTC Lambda via an S3 → SQS event.
3. Tails CloudWatch logs for both `ttc-lambda` and `ttc-augmentation-lambda` in real time, with a pinned spinner, until each emits its `REPORT RequestId:` end-of-invocation marker.
4. Fetches and pretty-prints the resulting TTC metadata JSON (`TTCMetadataV2/`) and augmented eICR XML (`AugmentationEICRV2/`) from S3.
5. Re-validates the augmented eICR and exits non-zero if any Schematron errors remain — asserting that augmentation resolved them.

### Usage

```sh
./scripts/aws_e2e.sh "<nonstandard test name>"
```

Example:

```sh
./scripts/aws_e2e.sh "Zucchini IgG"
```

You must have AWS credentials available in the environment (e.g. via `aws sso login` or `AWS_PROFILE`) with permissions to write to the `dibbs-text-to-code` bucket and read CloudWatch logs in `us-east-2`.

## Dependencies

| Tool                       | Why                                                                                                                                                                                                           |
| -------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `bash`                     | Script interpreter (uses `[[`, arrays, `BASH_REMATCH`).                                                                                                                                                       |
| `aws` (CLI v2)             | S3 uploads, `s3api head-object` polling, `logs tail`.                                                                                                                                                         |
| `gum`                      | Styled banners, spinners, log levels (Charm TUI library).                                                                                                                                                     |
| `unbuffer` (from `expect`) | Wraps `aws logs tail` in a PTY so its output line-buffers when piped. The AWS CLI v2 is a PyInstaller bundle that ignores `PYTHONUNBUFFERED`, so without `unbuffer` log lines arrive in one burst at the end. |
| `jq`                       | Pretty-prints JSON log payloads and the TTC metadata output.                                                                                                                                                  |
| `python3`                  | Templates the eICR (regex substitutions for displayName, originalText, and UUIDs). Standard library only.                                                                                                     |
| `uv`                       | Runs the in-repo `validation` package (real Schematron validation) via `uv run --project <repo> --all-packages`. Install: https://docs.astral.sh/uv/                                                          |
| `xmllint` (from `libxml2`) | Pretty-formats the augmented eICR XML output.                                                                                                                                                                 |
| `bat` _(optional)_         | Syntax-highlights the formatted XML. Falls back to plain output if missing.                                                                                                                                   |

### Install — macOS

All deps are available via Homebrew:

```sh
brew install awscli gum expect jq libxml2 bat
```

`python3` ships with macOS; if you want a newer one, `brew install python`.

### Install — Linux (Debian/Ubuntu)

```sh
# AWS CLI v2 — install from Amazon's bundle (the apt package is v1)
curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o awscliv2.zip
unzip awscliv2.zip && sudo ./aws/install

# Charm gum — add their apt repo
sudo mkdir -p /etc/apt/keyrings
curl -fsSL https://repo.charm.sh/apt/gpg.key | sudo gpg --dearmor -o /etc/apt/keyrings/charm.gpg
echo "deb [signed-by=/etc/apt/keyrings/charm.gpg] https://repo.charm.sh/apt/ * *" \
    | sudo tee /etc/apt/sources.list.d/charm.list
sudo apt update && sudo apt install gum

# The rest are in the default repos
sudo apt install expect jq libxml2-utils python3 bat

# On Debian/Ubuntu the `bat` binary is named `batcat`; symlink it:
mkdir -p ~/.local/bin && ln -s /usr/bin/batcat ~/.local/bin/bat
```

For Fedora/RHEL, swap `apt` for `dnf` and use `libxml2` instead of `libxml2-utils`.

### Install — Windows (WSL with Homebrew)

From inside your WSL shell (Linuxbrew installs to `/home/linuxbrew/.linuxbrew`):

```sh
brew install awscli gum expect jq libxml2 bat
```

The script is bash-only — run it from inside WSL, not from PowerShell or `cmd.exe`. Make sure your AWS credentials are configured inside WSL (`aws configure` or `aws sso login` from the WSL shell).

## Test fixtures

- `test_eicr.xml` — minimal eICR document used as the template input. Both scripts run real Schematron validation against the templated eICR (via the `validation` package) to produce the report uploaded to `ValidationResponseV2/`, rather than a canned fixture.

The script reuses the same generated filename across every S3 prefix; that's how the TTC and augmentation Lambdas correlate the schematron report, source eICR, and output objects for one invocation.

## `batch_aws_test.sh`

A batch-uploading bulk testing script for the DIBBs TTC Pipeline.

Given a JSON file of nonstandard test cases, this script:

1. Loads each test case from the file into a bash array.
2. Templates a dummy test eICR with the nonstandard input name of each test case, and stamps each result with a fresh UUID.
3. For each test eICR, one at a time, runs real Schematron validation against it and uploads that report plus the templated eICR to S3, which fires the TTC lambda via SQS event.
4. Tails both lambdas' CloudWatch logs in real time until each emits its `REPORT RequestId:` line (AWS's end-of-invocation marker).
5. Fetches the resulting augmented eICR XML from S3, parses its translated code name (where the TTC Pipeline leaves its predicted standardization), re-validates the augmented eICR, and marks the case passed only if the predicted code matches and no Schematron errors remain. Exits non-zero if any case fails.

### Usage

```sh
./scripts/batch_aws_test.sh ./scripts/PATH_TO_JSON_FILE_OF_TEST_CASES
```

Example:

```sh
./scripts/aws_e2e.sh ./scripts/test_cases_file.json
```

You must have AWS credentials available in the environment (e.g. via `aws sso login` or `AWS_PROFILE`) with permissions to write to the `dibbs-text-to-code` bucket and read CloudWatch logs in `us-east-2`.

## Dependencies

Depedencies and installation instructions for those dependencies are exactly the same as for the `aws_e2e.sh` script above.

## `load_test.sh`

An A/B load test for the deployed pipeline, built to prove that a change does (or does not) move performance — something `batch_aws_test.sh` cannot show, because it runs serially against a single warm Lambda container.

For one _arm_ (a deployed image version), the script:

1. Templates a corpus of a few hundred eICRs from the test-cases JSON. Each document's candidate text is **salted** with a unique run/arm/index marker (e.g. `K+, Whole Blood [lt-3f9a2c1b-baseline-042]`). The TTC result cache keys on a hash of the candidate text, so salting guarantees every document misses the cache and takes the full embedding + OpenSearch KNN path — no OpenSearch access is needed to reset state between runs or arms.
2. Generates the paired Schematron reports locally in a single Saxon process (reports are validated once per base case and reused when their content is document-independent).
3. Uploads all reports, then bursts the eICR uploads in parallel — forcing Lambda scale-out (SQS `batch_size = 1`, no reserved concurrency), which is what samples cold starts under load.
4. Waits for the pipeline to drain (all augmented eICRs present), then measures from the source of truth rather than by log-tailing:
   - **CloudWatch Logs Insights** over both lambdas' `REPORT` lines: duration p50/p90/p99, cold-start count, init duration, max memory, error count.
   - **End-to-end latency** per document from S3 `LastModified` (submission → augmented object).
   - **Correctness**: every augmented eICR's predicted LOINC translation vs. the expected code.
5. Writes a `results_<pass>.json` per pass and prints a summary.

With `--passes 2`, the second pass re-submits the _same salted texts_ under fresh filenames/UUIDs — pass 1 measures the cold-cache (full KNN) path, pass 2 the warm result-cache path.

### A/B protocol

```sh
# 1. Deploy the baseline (e.g. main) image, then:
./scripts/load_test.sh run --arm baseline --docs 300 --passes 2

# 2. Deploy the candidate branch image, then:
./scripts/load_test.sh run --arm branch --docs 300 --passes 2

# 3. Compare (repeat for p2):
./scripts/load_test.sh compare \
    load_test_runs/<run-id>-baseline/results_p1.json \
    load_test_runs/<run-id>-branch/results_p1.json
```

Each redeploy recycles all Lambda containers, so both arms get a fair cold-start sample. Run the arms close together in time, in a window with **no other traffic** to the lambdas — invocations are attributed to the run by time window, and the report warns when invocation counts exceed the document count.

Flags: `--docs` (default 300, max 900), `--passes` (default 1), `--concurrency` (parallel uploads, default 24), `--cases`, `--bucket` (default `dibbs-text-to-code`), `--out-dir` (default `load_test_runs/`, gitignored), `--drain-timeout` (default 1800s).

Dependencies: only `aws` (CLI v2), `uv`, and `bash` — no `gum`/`jq`/`unbuffer`. Helper logic lives in `load_test_corpus.py` (corpus + Schematron reports) and `load_test_report.py` (Logs Insights metrics, S3 latency join, correctness check, and the `compare` table).

## `ttc-reingestion-embeddings.sh`

Script for replacing the LOINC embeddings. It is invoked by the TTC reingestion GitHub Actions workflow (`workflow_dispatch` in `.github/workflows/ttc_reingestion.yml`) under the `ttc-reingestion-ci-role`, and is not meant to be run locally. The operator procedure, watchpoints, and recovery table can be found in [`docs/runbooks/reingest-loinc-embeddings.md`](../docs/runbooks/reingest-loinc-embeddings.md).

The script:

1. Halts TTC (reserved concurrency → 0, event source mapping disabled) and waits for in-flight SQS messages to drain (cap 20 min).
2. Drops and recreates both OpenSearch indices via `ttc-index-lambda` (`clear_index`, then `clear_result_cache`).
3. Backs up `ingestion/` to `ingestion-backup-<ts>/`, empties it, and syncs `reingestion/` in — those S3 writes are what trigger OSIS ingestion.
4. Polls the OpenSearch `_count` (cap 30 min) until the count has been stable for `--stability-polls` consecutive polls **and** equals `--expected-count`; a count above expected fails the run. The OSIS sink writes each document under a deterministic `_id` (`loinc_code|loinc_name_type`), so retries and redeliveries overwrite rather than duplicate and the count must land exactly.
5. Resumes TTC, restoring the original concurrency setting. If the resume fails, it publishes to `TTC_ALERT_TOPIC_ARN` — TTC is left halted and needs the runbook's manual resume.
6. Smoke tests: a fixed KNN query returns ≥ 1 hit, the input-queue backlog is draining, and DLQ depth is unchanged from the pre-run baseline.

Failures exit non-zero without rolling anything back; recover using the runbook's recovery table. Deleting the `ingestion-backup-<ts>/` prefix and clearing `reingestion/` are manual post-checks.

### Usage

```sh
./scripts/ttc-reingestion-embeddings.sh --expected-count <N> [--stability-polls <N>]
```

Requires `aws` (CLI v2), `curl` ≥ 7.75 (for `--aws-sigv4`), `jq`, and the `TTC_*` / `AWS_REGION` environment variables exported by the workflow (see the `env:` block in `.github/workflows/ttc_reingestion.yml`).

## Test Cases File Information

The batch testing script relies on a JSON file of curated test cases to process in-bulk. The file can contain any number of test cases, but the structure of the file should be a JSON dictionary with a single key-value pair, with key `"test_cases"` and a value of an array of dictionaries. Each dictionary in the array is expected to have three properties: `nonstandard_in` (the narrative, free-text string representing the nonstandard eICR input), `correct_standardized_code` (the true name variant of the LOINC code represented by the input), and `numeric_loinc_code` (a string giving the hyphenated digit string assigned to the code in the LOINC hierarchy).

Example:

```json
{
  "test_cases": [
    {
      "nonstandard_in": "blood urea nitrogen (BUN)",
      "correct_standardized_code": "Urea nitrogen [Mass/volume] in Blood",
      "numeric_loinc_code": "6299-2"
    },
    {
        ...
    },
    ...,
}
```
