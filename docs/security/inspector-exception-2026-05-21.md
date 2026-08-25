# AWS Inspector HIGH-severity Findings — Exception Request

**System:** DIBBs Text-to-Code (TTC) Lambda — `ttc-lambda` ECR image
**Date submitted:** 2026-05-21
**Requested review-by date:** 2026-06-20 (30-day HIGH remediation window)

## Summary

After the OS-toolchain CVEs were remediated in PR #571, AWS Inspector continues to report three HIGH-severity findings on `ttc-lambda:latest`. All three are Python-package CVEs marked `fixedInVersion: NotAvailable` upstream. They concern unsafe deserialization (`pickle` / `torch.load` / `.pt2`) of attacker-controlled serialized data. The TTC Lambda never accepts attacker-controlled serialized input — it only loads pre-baked SentenceTransformer models from `/opt/retriever_model` and `/opt/reranker_model`, which are downloaded at build time from the NCHS private Hugging Face repositories and persisted in the image as `safetensors`. Each finding is therefore a no-execution-path condition.

The Lambda also runs in a private-only VPC with no NAT/IGW (S3 access via VPC endpoint), and is invoked only by SQS from a trusted S3 prefix. There is no path for an external actor to deliver a malicious checkpoint or pickle to the function.

## Findings

### 1. CVE-2025-14929 — `transformers` 5.9.0 (X-CLIP checkpoint deserialization RCE)

- **CVSS 3.0:** 7.8 (AV:L/AC:L/PR:N/UI:R/S:U/C:H/I:H/A:H) — local, user-interaction-required
- **Vulnerable code path:** `transformers/models/x_clip/convert_x_clip_original_pytorch_to_hf.py` — a one-time conversion script that calls `torch.load` on an X-CLIP checkpoint path supplied by the caller.
- **No-execution-path argument:** TTC does not import, invoke, or expose this conversion script. TTC does not use the X-CLIP model class at all; its only models are the NCHS retriever (`ttc-retriever-v1.0`) and reranker (`ttc-reranker-mvp`), both loaded via `sentence-transformers` from `safetensors` files baked into the image at build time.
- **Upstream status:** Originally disclosed via ZDI-CAN-28308. NVD lists 5.0.0-rc0 explicitly; no patched version has been released as of 2026-05-21. No public Hugging Face security advisory or merged PR addresses this CVE yet.
- **Reference:** https://nvd.nist.gov/vuln/detail/CVE-2025-14929

### 2. CVE-2026-4538 — `torch` 2.9.1+cpu (`torch.export.load` arbitrary code execution via crafted `.pt2`)

- **CVSS 3.1:** 7.8 (local, user-interaction-required)
- **Vulnerable code path:** `torch.export.load` / the `pt2` loading handler — unsafe deserialization of `ExportedProgram` artifacts.
- **No-execution-path argument:** TTC never calls `torch.export.load` (or `torch.load` on user input). Inference runs through `SentenceTransformer.encode`, which loads `safetensors` at cold-start from the baked-in model directory. No `.pt2` files exist in the image and the runtime never reads serialized torch artifacts from any S3 prefix, SQS payload, or other external source.
- **Upstream status:** The proposed fix, [pytorch/pytorch#176791](https://github.com/pytorch/pytorch/pull/176791) (adding a `weights_only` default to `torch.export.load`), was **closed unmerged** on 2026-03-15. No alternative PR has been opened. PyTorch's general guidance is in the Security Policy at https://github.com/pytorch/pytorch/blob/main/SECURITY.md — load only trusted serialized artifacts.
- **Reference:** https://nvd.nist.gov/vuln/detail/CVE-2026-4538

### 3. CVE-2024-34997 — `joblib` 1.5.3 (`NumpyArrayWrapper` pickle.load) — **disputed / false positive**

- **CVSS 3.x:** 7.5 (per NVD)
- **Vulnerable code path:** `joblib.numpy_pickle.NumpyArrayWrapper.read_array` — calls `pickle.load` on cached array data.
- **No-execution-path argument:** TTC does not call `joblib.load` on any external input. `joblib` enters the dependency graph only as a transitive of `scikit-learn` / `sentence-transformers` internals (inter-process communication during model loading); no `joblib` cache file is read from S3, SQS, or other untrusted sources.
- **Upstream status:** **Confirmed false positive by joblib maintainers.** Disputed on MITRE.
  - Maintainer Thomas Moreau ([joblib#1588](https://github.com/joblib/joblib/issues/1588)): _"The CVE is indeed a false positive as it is only due to our use of pickle for inter process communication. While it is unsafe to use it for sharing content between untrusted parties, it is not used for that in joblib."_
  - Maintainer Gaël Varoquaux: _"It's not a vulnerability, not any more than running Python files is, or importing Python modules."_
  - The issue is intentionally left open as a tracking issue for the MITRE disposition: [joblib#1588](https://github.com/joblib/joblib/issues/1588), [joblib#1690](https://github.com/joblib/joblib/issues/1690).
- **Reference:** https://nvd.nist.gov/vuln/detail/CVE-2024-34997

## Compensating controls

- **Sealed model supply chain:** retriever and reranker weights are pinned to NCHS private Hugging Face repos, downloaded at image build time with a secret-mounted token, and shipped inside the image. Runtime never re-downloads or reads model weights from untrusted sources.
- **Network isolation:** Lambda runs in a private-only VPC (no NAT/IGW); S3 reads/writes traverse a Gateway VPC endpoint. No outbound internet.
- **Constrained invocation surface:** triggered exclusively by SQS messages bound to known eICR S3 prefixes; payload schema validated before any model invocation.
- **No pickle/`.pt2`/joblib reads at runtime:** code review confirms there are no calls to `torch.load`, `torch.export.load`, `pickle.load`, or `joblib.load` on request-derived paths.

## Review cadence

Per the 30-day HIGH remediation window we will:

1. Re-scan all three Lambda images against AWS Inspector on or before **2026-06-20**.
2. If any of the three CVEs has been resolved upstream (new `transformers`/`torch`/`joblib` release with the fix, or MITRE rejection for CVE-2024-34997), rebuild and republish to clear the finding.
3. If still unfixed upstream, resubmit this exception with refreshed upstream status.
