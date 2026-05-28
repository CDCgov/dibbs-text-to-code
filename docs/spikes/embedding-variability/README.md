# Embedding Variability Spike

Quantifies how much the `NCHS/ttc-retriever-mvp` retriever's 1024-dim output drifts across
five compute environments for a fixed subset of ~500 LOINC display-name strings, and whether
that drift is large enough to change the LOINC code returned by the prod KNN search.

The five environments under test:

| Env key      | Source                                                                                     |
| ------------ | ------------------------------------------------------------------------------------------ |
| `azure_gpu`  | Already in the prod OpenSearch index (`description_vector` field). Reference baseline.     |
| `azure_cpu`  | Pre-generated at `~/Downloads/cpu_vector_test.json`. The KEYS define the working subset.   |
| `mac_cpu`    | Re-embed locally with `SentenceTransformer(..., device="cpu")` on this Mac.                |
| `mac_mps`    | Re-embed locally with `device="mps"` (Apple Metal).                                        |
| `aws_lambda` | Re-embed inside the production `Dockerfile.ttc` image (x86_64, CPU torch, baked model).    |

The end product is `outputs/report.html` — a single self-contained Plotly page with
pairwise cosine / L2 distributions, an outlier table, and a 5×5 downstream KNN top-1
agreement matrix.

---

## One-time setup

```sh
# Sync the workspace so all packages' deps land in .venv
just bootstrap   # or: uv sync

# Plotly + pandas aren't workspace deps; install them into the workspace venv ad-hoc
VIRTUAL_ENV="$(pwd)/.venv" uv pip install plotly pandas
```

`sentence-transformers`, `opensearch-py`, `requests-aws4auth`, `boto3`, `numpy`, and
`tqdm` are already workspace deps and resolve through `uv run` (boto3 is owned by the
`lambda-handler` package, so the S3 fetcher uses `uv run --package lambda-handler`).

---

## Reproduction

All commands are run from the repo root.

### 1. Lay down the canonical subset (azure_cpu)

```sh
cp ~/Downloads/cpu_vector_test.json \
   docs/spikes/embedding-variability/outputs/vectors_azure_cpu.json
```

### 2. Mac CPU and MPS

```sh
uv run python docs/spikes/embedding-variability/embed_local.py \
  --device cpu \
  --inputs docs/spikes/embedding-variability/outputs/vectors_azure_cpu.json \
  --output docs/spikes/embedding-variability/outputs/vectors_mac_cpu.json

uv run python docs/spikes/embedding-variability/embed_local.py \
  --device mps \
  --inputs docs/spikes/embedding-variability/outputs/vectors_azure_cpu.json \
  --output docs/spikes/embedding-variability/outputs/vectors_mac_mps.json
```

Each run takes a few minutes on an M4 Pro. MPS failures (if any) are logged to
`outputs/mps_failures.json`; if more than ~5% fail, `mac_mps` is dropped from the analysis.

### 3. Azure GPU vectors

Two fetchers are available — both reach the same vectors:

**From prod OpenSearch directly** — the prod domain has a public HTTPS endpoint with
IAM auth. Requires AWS creds with `es:ESHttpGet`.

```sh
OPENSEARCH_ENDPOINT_URL="https://search-ttc-os-domain-...us-east-2.es.amazonaws.com" \
AWS_REGION="us-east-2" \
INDEX_NAME="ttc-index" \
uv run python docs/spikes/embedding-variability/fetch_azure_gpu.py \
  --inputs docs/spikes/embedding-variability/outputs/vectors_azure_cpu.json \
  --output docs/spikes/embedding-variability/outputs/vectors_azure_gpu.json
```

**From S3 ingestion NDJSON** — alternative path that streams the OSIS source files
(`s3://dibbs-text-to-code/ingestion/*.jsonl`) and pulls only the matching descriptions.
Useful if OpenSearch access isn't available.

```sh
uv run python docs/spikes/embedding-variability/fetch_azure_gpu_from_s3.py \
  --inputs docs/spikes/embedding-variability/outputs/vectors_azure_cpu.json \
  --output docs/spikes/embedding-variability/outputs/vectors_azure_gpu.json
```

Either fetcher writes any descriptions not found to `outputs/azure_gpu_misses.json`.

### 4. AWS Lambda runtime (Docker reproduction)

Build the prod Lambda image once, then a tiny overlay that runs an embedding script:

```sh
# Build the existing TTC Lambda image (~5 min; needs HuggingFace token)
HF_TOKEN="<your-token>" docker build \
  --secret id=huggingface_token,env=HF_TOKEN \
  -f Dockerfile.ttc \
  -t ttc-embed:local \
  .

# Build the spike overlay (instant)
docker build \
  -f docs/spikes/embedding-variability/embed_lambda_docker/Dockerfile.embed-spike \
  -t ttc-embed-spike:local \
  docs/spikes/embedding-variability/embed_lambda_docker

# Run on linux/amd64 (Rosetta on M-series) to mirror the prod Lambda arch
docker run --rm --platform linux/amd64 \
  -v "$(pwd)/docs/spikes/embedding-variability/outputs:/work" \
  -e INPUT_PATH=/work/vectors_azure_cpu.json \
  --entrypoint python ttc-embed-spike:local /var/task/embed_in_lambda.py
```

Output lands at `outputs/vectors_aws_lambda.json`. Runtime is ~5–15 min via Rosetta.

### 5. Analyze + generate the report

```sh
# Pairwise metrics + outlier ranking + downstream KNN agreement (real prod index)
OPENSEARCH_ENDPOINT_URL="https://search-ttc-os-domain-...us-east-2.es.amazonaws.com" \
AWS_REGION="us-east-2" \
INDEX_NAME="ttc-index" \
uv run python docs/spikes/embedding-variability/analyze.py --with-knn

# OR: no-network proxy (in-memory KNN over the same 500-row subset)
# uv run python docs/spikes/embedding-variability/analyze.py --with-offline-knn

# Self-contained HTML
uv run python docs/spikes/embedding-variability/generate_report.py

open docs/spikes/embedding-variability/outputs/report.html
```

`--with-knn` issues 5 × 500 = 2500 KNN queries against the prod `ttc-index` (~1.7M docs)
and records the top-1 LOINC code per (env, description) — the right default when prod is
reachable, ~45 s per env. `--with-offline-knn` is a no-network fallback that builds an
in-memory KNN over just the 500-row subset.

---

## Caveats

- **Exact match on `description`** — the prod index has no `.keyword` subfield, so the
  fetcher uses `match_phrase` and post-filters on `_source.description == desc`. Same-token-set
  collisions show up as misses.
- **Subset bias** — `analyze.py` operates on the intersection of descriptions present across
  all 5 envs. Coverage is reported up-front in the HTML.
- **Normalization** — production calls `.encode(text)` with default args, no L2 normalization.
  Cosine similarity is computed on raw vectors throughout.
- **GPU non-determinism** — the Azure GPU vectors are a single snapshot. Running the
  same model on the same GPU twice is not bitwise deterministic; the report only captures
  the snapshot we have.
- **MPS partial support** — `sentence-transformers` on Apple Metal occasionally hits
  unsupported ops; per-item failures are tolerated.
