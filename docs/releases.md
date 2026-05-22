# Releases

Releases are driven by the `version` field in the root `pyproject.toml`. Bumping
that field on `main` triggers automation that tags the merge commit, builds and
publishes the three Lambda images (`index`, `ttc`, `augmentation`) to GHCR and
APHL ECR, creates a GitHub Release with auto-generated notes, and posts the
release link to Slack.

## Cut a release

1. Decide the next [semver](https://semver.org/) version (`X.Y.Z`):
   - **Patch (`X.Y.Z+1`)**: backwards-compatible bug fixes.
   - **Minor (`X.Y+1.0`)**: backwards-compatible new functionality.
   - **Major (`X+1.0.0`)**: incompatible API changes.
2. Open a PR titled `Release vX.Y.Z` that bumps `version` in the root
   `pyproject.toml` to `X.Y.Z`. Do not include a `v` prefix in the file; the
   workflow prepends it when tagging.
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

## Failure modes

- **Tag `vX.Y.Z` already exists at a different commit**: the workflow fails
  loudly during the `detect-release` job. Bump to the next available version
  in a new PR.
- **Partial failure (tag and images created, release step failed)**: re-run
  the workflow from the Actions tab. The collision check treats a same-SHA tag
  as a no-op, so re-runs are idempotent.
- **Non-semver version**: the workflow rejects pre-release suffixes
  (e.g. `1.0.0-rc.1`). Use a strict `X.Y.Z` format.

## Release notes

GitHub auto-generates notes from PRs merged since the previous `vX.Y.Z` tag.
The category and exclusion rules live in [.github/release.yml](../.github/release.yml);
PRs labeled `ignore-for-release` are excluded.

For more on customizing release notes, see GitHub's
[automatically generated release notes](https://docs.github.com/en/repositories/releasing-projects-on-github/automatically-generated-release-notes)
documentation.
