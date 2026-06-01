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

The end product is `outputs/report.html` — a single self-contained Plotly page organized
around the four questions below, with pairwise cosine / L2 distributions, an outlier table,
and 5×5 downstream KNN agreement matrices (top-1, top-10 set, and top-10 ordering) plus
per-candidate score stability and a search-engine determinism baseline.

---

## Findings & recommendation

> TL;DR: **The compute environment is not a meaningful source of variability for the TTC
> retriever on this corpus.** Recommendation: **no action** — don't re-embed the index on CPU,
> and a CPU/GPU vector swap does not need to be raised with APHL.

The investigation answers four questions about CPU-vs-GPU embedding variability. The
production-relevant comparison throughout is `azure_gpu` (the vectors in the index) vs
`aws_lambda` (the production Lambda runtime). Numbers below are from the 500-string subset.

**Q1 — How different are the vectors?** Negligibly. Embedding the same string on Azure GPU vs
AWS CPU differs by ~`6.5e-06` in L2 distance and ~`2.3e-11` in cosine distance — the float32
precision floor. The model's normalization layer keeps vectors ~unit length, so an L2 move in
the sixth decimal place is real at that scale but leaves cosine similarity virtually 1.0. The
numbers still mean the same thing on CPU or GPU.

**Q2 — Do those differences change the retriever's (OpenSearch) results?** No, in every way that
matters. Across all 5 environments and 500 strings:

| Signal | Result |
| --- | --- |
| Top-1 retrieved LOINC agreement | **100%** on every environment pair |
| Top-10 candidate-set overlap (Jaccard) | 99.86% – 100% |
| Top-10 exact-order agreement | 99.2% – 99.8% |
| Per-candidate score delta vs `azure_gpu` (matched by doc id) | mean ~`1.3e-07`, max ~`2.3e-06` |

Crucially, OpenSearch KNN is an *approximate* (HNSW) search: re-querying the **identical**
`azure_gpu` vectors a second time already yields top-1 100% / set 99.975% / order 99.8% — so the
deep-rank (4–10) reshuffles the review anticipated do occur, but at a rate **indistinguishable
from the search engine's own re-query noise**, and never disturb the top-1. The one description
that flipped top-1 in an earlier run (`"MR Hrt Cine for Flow VM"`) is an **exact score tie**
between `39140-9` and `105173-9` (both ≈ 1.0, margin 0.00) — rank order is decided arbitrarily by
index internals, not by the embedding.

**Q3 — Are the final pipeline (retriever + reranker) predictions different?** Not measured. The
reranker does its own internal embedding and could, in principle, re-score an identical candidate
list differently across environments (an "embedding cascade"). Two facts bound the risk: (a) the
retriever is the dominant, trusted component and is environment-invariant per Q1–Q2; (b) planned
confidence/margin thresholds will short-circuit the reranker when the retriever is already
confident. Flagged as an open item, not a blocker.

**Q4 — Would swapping the index to Azure-CPU vectors help?** Not run. A proper answer is the
brute-force pairwise experiment over all ~335k LOINC variants, which is disproportionate to the
size of the concern given Q1–Q2. Revisit only if production data surfaces instability.

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

`--with-knn` issues a top-10 KNN query for every (env, description) against the prod
`ttc-index` (~335k docs), recording each hit's LOINC code, document id, and score (~45 s per
env). From this it computes the top-1 agreement matrix, the top-10 set-Jaccard and
exact-order agreement matrices, and the per-document score delta vs the `azure_gpu` reference.
It also re-queries the reference env's vectors once more to establish the approximate-search
**determinism baseline** (identical input, possibly different output) that the cross-env
numbers are read against. `--with-offline-knn` is a no-network fallback that builds an
in-memory top-1 KNN over just the 500-row subset.

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
- **Approximate-search determinism floor** — OpenSearch KNN (HNSW) is approximate, and the
  prod index is a live, periodically re-ingested corpus. Re-querying identical vectors does
  not return a perfectly identical result list, so cross-env retrieval differences are read
  against a measured determinism baseline rather than assumed to be embedding drift.
- **Reranker stage not measured (Q3)** — only the retriever (KNN) is exercised here; the
  reranker's environment sensitivity is out of scope for this spike.
- **MPS partial support** — `sentence-transformers` on Apple Metal occasionally hits
  unsupported ops; per-item failures are tolerated.
