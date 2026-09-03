# Releases

Releases are driven by the `version` field in the root `pyproject.toml`. Bumping
that field on `main` triggers automation that tags the merge commit, builds and
publishes the three Lambda images (`index`, `ttc`, `augmentation`) to GHCR and
APHL ECR, creates a GitHub Release with auto-generated notes, and posts the
release link to Slack.

## Lifecycle at a glance

1. [Model updates](#model-updates): only when a new retriever or reranker ships.
2. [Cut a release](#cut-a-release).
3. [Verification](#verification).
4. [Deploy to APHL](#deploy-to-aphl).

## Model updates

Skip this section if the release does not change the retriever or reranker.

A new model changes the vector space, so the LOINC embeddings in OpenSearch
must be regenerated with that model and reloaded in every environment that
runs TTC: ours, and APHL's dev, test, and prod.

### Publish the model

1. Fine-tune in the Azure ML training workspace and push the trained model to
   Hugging Face as `NCHS/ttc-retriever-vX.Y` (reranker: `NCHS/ttc-reranker-vX.Y`).
2. In the release PR, bump `RETRIEVER_MODEL_VERSION` (and/or
   `RERANKER_MODEL_VERSION`) in `Dockerfile.ttc` and in
   `packages/text-to-code/src/text_to_code/models/registry.py`. Update the
   model link in `README.md`.

### Regenerate the LOINC embeddings

1. Run the `embedding.ipynb` notebook in the Azure ML workspace against the new
   retriever and download the `.jsonl` files it writes.
2. Compute the expected document count and keep it with the files. Each line 
   is one OpenSearch document, keyed on
   `loinc_code|loinc_name_type`, so the index count must equal the total line
   count exactly:

   ```sh
   cat embeddings/*.jsonl | wc -l
   ```

### Reingest into our AWS environment

1. Stage the files under the `reingestion/` prefix. Nothing watches that
   prefix, so this is safe to do at any time:

   ```sh
   aws s3 sync ./embeddings/ s3://dibbs-text-to-code/reingestion/
   ```

2. From the Actions tab, run the `TTC reingestion` workflow with
   `expected_count` set to the number above. The workflow halts TTC, clears
   both OpenSearch indices (vector search and result cache) via the index
   Lambda, promotes `reingestion/` to `ingestion/`, waits for the ingestion
   pipeline to reach the expected count, and resumes TTC. See the
   [re-ingestion runbook](runbooks/reingest-loinc-embeddings.md) for the
   step-by-step, watchpoints, and recovery.
3. Do this before or alongside the release so our environment runs the new
   image against matching embeddings.

### Package the embeddings for APHL

APHL does not have a reingestion workflow yet; their infrastructure engineer
runs the equivalent steps by hand.

1. Zip the .jsonl files and upload the archive to the Skylight shared Google Drive.
2. Send the Drive link and the expected document count to APHL's
   infrastructure engineer on Teams.
3. For each environment, APHL then:
   - invokes `ttc-index-lambda` with `{"action":"clear_index"}` and again with
     `{"action":"clear_result_cache"}`. Both are required; if the result cache
     survives, cached matches from the previous model keep being served.
   - uploads the shards to that environment's `ingestion/` prefix, which their
     ingestion pipeline consumes.
   - confirms the index document count matches the expected count.

> [!IMPORTANT]
> The new image and the new embeddings must land in each APHL environment in
> the same maintenance window. An old model querying new embeddings, or the
> reverse, returns wrong matches with no error.

## Cut a release

1. Decide the next [semver](https://semver.org/) version (`X.Y.Z`):
   - **Patch (`X.Y.Z+1`)**: backwards-compatible bug fixes.
   - **Minor (`X.Y+1.0`)**: backwards-compatible new functionality.
   - **Major (`X+1.0.0`)**: incompatible API changes.
2. Open a PR titled `Release vX.Y.Z` that bumps `version` in the root
   `pyproject.toml` to `X.Y.Z`. Do not include a `v` prefix in the file; the
   workflow prepends it when tagging.
   - If the release includes a model update, the same PR carries the model
     version bump from [Publish the model](#publish-the-model).
3. Get review and merge to `main`.
4. The `release` workflow runs automatically on the merge commit:
   - tags the merge commit as `vX.Y.Z`
   - builds all three Lambda images for `linux/amd64`
   - pushes `vX.Y.Z`, `vX.Y`, `vX`, and `latest` tags to GHCR
   - pushes `vX.Y.Z` and `latest` to APHL ECR (APHL ECR has tag
     immutability enabled on everything but `latest`, so the floating
     `vX.Y` / `vX` tags can't be re-pointed there)
   - publishes a GitHub Release named `vX.Y.Z` with auto-generated notes
   - posts the release link to Slack

On GHCR, the `vX.Y` and `vX` tags float to the latest release within that
line; the `vX.Y.Z` tag is immutable. On APHL ECR every tag except
`latest` is immutable.

### Hotfix

Same flow. Open a PR that bumps the patch number (e.g. `0.2.0` to `0.2.1`) and
merge.

## Verification

After merging a release PR, confirm:

- [ ] **Actions tab**: the `release` workflow run on the merge commit is green.
- [ ] **Tags**: `git fetch --tags && git tag -l "vX.Y.Z"` shows the new tag.
- [ ] **GitHub Releases**: `vX.Y.Z` is published (not draft) with PR-list notes.
- [ ] **APHL ECR**: each of `index`, `ttc`, `augmentation` has `vX.Y.Z`
      and `latest` tags.
- [ ] **GHCR**: each image additionally has `vX.Y` and `vX` floating tags
      pointing at this release.
- [ ] **Slack**: the release-notifications channel received the release link.

## Deploy to APHL

The images in APHL ECR are not deployed anywhere until APHL promotes them.
Slack is notified automatically; APHL is not.

1. **Notify APHL.** Post on Teams to APHL's release contacts that `vX.Y.Z` is
   in APHL ECR and ready for release. Include the GitHub Release link. For a
   model update, also include the embeddings Drive link and the expected
   document count.
2. **Security scan.** APHL's release engineer reviews the AWS Inspector scan of
   the three images. CRITICAL and HIGH findings are handled case by case: either bump the
   dependency and cut a patch release, or write an exception note under
   [`docs/security/`](security/inspector-exception-2026-05-21.md) for APHL
   security to accept.
3. **dev, then test.** APHL's release engineer deploys the version to dev, then
   test, and checks that TTC processes traffic normally. For a model update,
   the embeddings reload happens in the same window in each environment (see
   [Model updates](#model-updates)).
4. **Change control for prod.** APHL's change control board meets every
   Tuesday. Once test looks good, their release engineer files a change request
   for the next meeting. Plan for at least a week between "ready for release"
   and prod.
5. **Prod.** After the board approves, the version (and embeddings, for a
   model update) goes to prod in the same window.

The release is done when:

- [ ] APHL prod is running `vX.Y.Z`.
- [ ] For a model update, the prod index document count matches the expected
      count.
- [ ] No TTC or ingestion DLQ alarms fired after the window.

## Failure modes

- **Tag `vX.Y.Z` already exists at a different commit**: the workflow fails
  loudly during the `detect-release` job. Bump to the next available version
  in a new PR.
- **Partial failure (tag and images created, release step failed)**: re-run
  the workflow from the Actions tab. The collision check treats a same-SHA tag
  as a no-op, so re-runs are idempotent.
- **Non-semver version**: the workflow rejects pre-release suffixes
  (e.g. `1.0.0-rc.1`). Use a strict `X.Y.Z` format.
- **Inspector CRITICAL/HIGH findings after release**: the release is not blocked
  outright. Decide with APHL's release engineer between a dependency fix plus
  patch release and an exception note, as described in
  [Deploy to APHL](#deploy-to-aphl).

## Release notes

GitHub auto-generates notes from PRs merged since the previous `vX.Y.Z` tag.
The category and exclusion rules live in [.github/release.yaml](../.github/release.yaml);
PRs labeled `ignore-for-release` are excluded.

For more on customizing release notes, see GitHub's
[automatically generated release notes](https://docs.github.com/en/repositories/releasing-projects-on-github/automatically-generated-release-notes)
documentation.
