# Inference Service

HTTP service that serves the Text to Code retriever and reranker models on a GPU. The TTC
Lambda calls it instead of loading the models in-process when `INFERENCE_SERVICE_URL` is
set. In AWS it runs on ECS Managed Instances (see `terraform/inference.tf`).

## Endpoints

| Method | Path      | Purpose                                                                  |
| ------ | --------- | ------------------------------------------------------------------------ |
| `GET`  | `/health` | `200` once both models are loaded, `503` while loading                   |
| `GET`  | `/info`   | Model URIs, device, dtype, embedding dimension, torch/CUDA versions      |
| `POST` | `/embed`  | `{"texts": [...]}` to one retriever embedding per text                   |
| `POST` | `/rank`   | `{"query": "...", "documents": [...]}` to reranker scores, highest first |

Request and response models live in `shared_models.inference`.

## Configuration

| Variable              | Default   | Purpose                                                                  |
| --------------------- | --------- | ------------------------------------------------------------------------ |
| `RETRIEVER_MODEL_URI` | required  | `s3://bucket/prefix/`, local directory, or Hugging Face repo id          |
| `RERANKER_MODEL_URI`  | required  | Same forms as the retriever                                              |
| `MODEL_DTYPE`         | `float32` | `float32`, `float16`, or `bfloat16`                                      |
| `MODEL_DEVICE`        | `cuda`    | `cuda`, `cpu`, or `mps`. With `cuda`, startup fails if no GPU is visible |
| `MODEL_CACHE_DIR`     | `/models` | Where remote models are downloaded                                       |
| `PORT`                | `8080`    | Listen port                                                              |

Models are loaded at startup, so swapping a model means pointing a URI at a different
prefix and restarting the service. No image rebuild is needed.

## Running locally

```sh
RETRIEVER_MODEL_URI=models/ttc-retriever-v1.0 \
RERANKER_MODEL_URI=models/ttc-reranker-v1.0 \
MODEL_DEVICE=cpu MODEL_CACHE_DIR=/tmp/ttc-models \
  uv run --package inference-service python -m inference_service
```

Then point the TTC code at it with `INFERENCE_SERVICE_URL=http://localhost:8080`.

## CPU/GPU parity check

`python -m inference_service.parity --cases <path or s3:// URI>` loads the configured models
on both the GPU and the CPU and compares embeddings and reranker output for the cases in
`scripts/test_cases.json` format. See `docs/runbooks/inference-service-dev.md`.
