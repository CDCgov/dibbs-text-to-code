# Runbook: GPU Inference Service (Skylight dev)

**Audience:** Engineers working with the GPU inference service in the Skylight AWS dev stack.
**Scope:** The `ttc-inference` ECS service defined in `terraform/inference.tf`, the `packages/inference-service` package, and the TTC Lambda's use of it. The demo API Lambda does not use the service.

## How it works

The TTC Lambda sends the two model calls (retriever embedding and reranker scoring) to an HTTP service running on one `g6.xlarge` (NVIDIA L4, 24 GB GPU memory) on ECS Managed Instances. Everything else (S3, SQS, OpenSearch, the result cache) is unchanged, so lab texts that are already cached never reach the GPU.

The service scales to zero:

1. A message lands on the TTC input queue. Within about 1 to 3 minutes the `ttc-inference-wake` alarm sets the service's desired count to 1.
2. ECS launches a GPU instance, pulls the image, and starts the task. The task downloads the models from S3, loads them on the GPU, and only then reports healthy and registers `inference.ttc.internal`.
3. Meanwhile the TTC Lambda retries the connection for up to `inference_ready_timeout_seconds` (12 minutes). If the service is still not up, the Lambda returns the message to the queue with a 60 second visibility timeout instead of writing a passthrough, so the eICR is retried rather than passed through uncoded. A message that fails this way three times lands in the DLQ and alerts Slack.
4. When the queue has been empty for `inference_idle_minutes` (15), the `ttc-inference-sleep` alarm sets the desired count to 0. ECS terminates the idle instance after `inference_instance_idle_seconds` (10 minutes).

A measured cold start with the v1.0 models (October 2026), from eICR upload to a healthy service, took about 6.5 minutes:

| Step | Elapsed |
|---|---|
| Wake alarm fires, GPU instance launched | 3:25 |
| Task placed on the instance | 3:50 |
| Image pulled, container started | 5:40 |
| Models downloaded from S3 (3.6 GB) and loaded on the GPU | 6:00 |
| Health check passes, `inference.ttc.internal` resolves | 6:35 |

Most of it is the SQS metric delay before the alarm fires and the image pull. Larger models mainly add download time.

> [!NOTE]
> ECS Managed Instances hides its EC2 instances from default listings (`HiddenByDefault`), so a filtered `aws ec2 describe-instances` does not show the GPU instance. Use `aws ecs list-container-instances --cluster ttc-inference` and `aws ecs describe-container-instances`, or `aws ec2 describe-instances --instance-ids <id>`.

**Cost:** about $0.85/hour while the GPU instance runs (on-demand `g6.xlarge` plus the Managed Instances fee). Nothing while it is scaled to zero, apart from the NAT gateway (about $33/month), which the TTC Lambda also needs to reach OpenSearch.

## Day-to-day commands

All of these run against the default stack and need AWS credentials for account 339712971032.

```sh
just inference status    # desired/running tasks, alarm states, recent scaling activity
just inference logs      # follow /ecs/ttc-inference
just inference wake      # start it now and hold it up (suspends scale-in)
just inference release   # let the idle alarm scale it to zero again
just inference sleep     # stop it now
```

`wake` is for manual testing. It keeps the GPU running until you run `release` or `sleep`, so don't leave it held. The next CI apply does not clear the hold, because Terraform ignores the scalable target's suspended state.

Sending an eICR through the pipeline (for example `./scripts/aws_e2e.sh "<lab name>"`) wakes the service on its own. Use a lab name that is not already in the result cache, or the GPU is never called.

## Swapping models

Models are loaded at task start from S3, so a swap needs no image rebuild.

1. Upload the model directory (a saved sentence-transformers model) to a **new** prefix. Never overwrite an existing prefix: TTC metadata records the URI as the model ID, so the URI has to identify one set of weights.

   ```sh
   just inference upload-model ttc-reranker-v2.0 /path/to/ttc-reranker-v2.0
   ```

2. Point Terraform at it in `terraform/terraform.tfvars` (or with `-var`):

   ```hcl
   inference_reranker_model_uri = "s3://dibbs-text-to-code/models/ttc-reranker-v2.0/"
   ```

   The same variable is used for the Lambda's `RERANKER_MODEL_PATH`, so TTC metadata reports the new model.

3. Apply. The task definition gets a new revision and the service replaces its task. A running task is stopped before the new one starts (there is only ever one GPU), so requests in that window wait for the new task like a cold start.

To use larger models, `inference_model_dtype` switches both models to `bfloat16` or `float16`. Check that the weights fit in the task's 12 GiB of host memory while loading, and in the 24 GB of GPU memory.

> [!WARNING]
> **A reranker swap is self-contained. A retriever swap is not.** The OpenSearch index stores LOINC embeddings produced by the retriever, so a new retriever needs the corpus re-embedded with that model and reingested ([reingest-loinc-embeddings.md](reingest-loinc-embeddings.md)). A retriever with a different embedding size also needs the index dimension changed: it is hard-coded to 1024 in `packages/index-lambda/src/index_lambda/lambda_function.py` and `scripts/ttc-reingestion-embeddings.sh`. Swapping the retriever URI without both produces confidently wrong matches, not errors.

## Checking GPU/CPU parity

The production corpus and the baked-in Lambda models run on CPU, so GPU results should be compared before trusting a new deployment:

```sh
just inference wake
just inference parity    # needs the AWS CLI Session Manager plugin
just inference release
```

`parity` uploads `scripts/test_cases.json` to `s3://dibbs-text-to-code/parity/` and runs `python -m inference_service.parity` inside the running task. That command loads the served models on both the GPU and the CPU and reports the largest embedding cosine distance, the share of queries whose top reranked document matches, and the largest reranker score difference. It exits non-zero if the top-1 agreement is below 100% or the cosine distance is above `1e-6`.

For an end-to-end comparison, run the same eICR with `-var ttc_use_inference_service=false` (models in the Lambda) and with it on, and diff the `TTCMetadataV2/` outputs. Delete that input's entries from the `ttc-result-cache` index before the second run, otherwise it is a cache hit and compares nothing.

## Turning it off

Set `ttc_use_inference_service = false` and apply. The TTC Lambda goes back to the models baked into its image. The ECS service stays deployed at zero tasks and costs nothing.

## Troubleshooting

**The service never starts after a message arrives.** Run `just inference status`. If the wake alarm is in `ALARM` but the desired count is 0, check the scaling activity for an error. If the desired count is 1 but nothing is running, check `aws ecs describe-services --cluster ttc-inference --services ttc-inference --query 'services[0].events[:5]'`. Common causes:

- No GPU capacity, or a "Running On-Demand G and VT instances" vCPU quota below 4. Check with `aws service-quotas get-service-quota --service-code ec2 --quota-code L-DB2E81BA`.
- The instance role cannot be passed: an `iam:PassRole` error on the infrastructure role.

**The task starts and then exits.** Read `just inference logs`. `MODEL_DEVICE=cuda but CUDA is not available` means the image's CUDA build does not match the instance's NVIDIA driver; rebuild with a different `TORCH_INDEX_URL` build arg in `Dockerfile.inference`. `No model files found at s3://...` means the model URI is wrong or the upload is missing. After repeated failures the deployment circuit breaker rolls back to the previous task definition.

**TTC Lambda logs show `waiting_for_inference_service` and then `inference_unavailable` instead of `inference_service_ready`.** The cold start took longer than `inference_ready_timeout_seconds`. The message is retried about a minute later, by which point the service is usually up. If it keeps happening, look at where the time goes in the task logs (image pull, model download, model load) before raising the timeout.

**The GPU stays up with nothing to do.** Something is keeping messages on the TTC input queue (check its visible and in-flight counts), or a `just inference wake` hold was never released (`just inference status` shows `DynamicScalingInSuspended: True`).
