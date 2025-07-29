# Releases

This document outlines our release process, from the automatic creation of draft releases to the tagging and publishing of final releases.

## 1. Draft Release Creation

Whenever pull requests are merged into the `main` branch, a new **draft release** is automatically generated. This draft is based on the differences between the last official release and the current state of the `main` branch.

- Only **one draft release** is maintained at any given time, tracking all upcoming changes.
- As more pull requests are merged, the existing draft release is updated with the new changes. This ensures that the draft release always reflects the latest features, fixes, and updates heading to production.

## 2. Release Tagging and Publishing

To publish a release, a developer with the appropriate permissions pushes a release tag. The tag format is structured using
the [Semantic Versioning](https://semver.org/) convention:

`vMM.mm.pp`

- **MM**: Version when you make an incompatible API change.
- **mm**: Version when you add functionality in a backwards-compatible manner.
- **pp**: Version when you make backwards-compatible bug fixes.

#### Publishing Process:
- When a developer pushes a release tag, the process automatically publishes the existing draft release with the corresponding tag.
- **Only users with the `maintain` or `admin` role** can push version tags, ensuring controlled and authorized release management.

Example:

```sh
$ git checkout main
$ git pull
$ git tag -a "v[MM].[mm].[pp]" -m"v[MM].[mm].[pp]"
$ git push --tags
```

### 3. Release Notes

Our release descriptions are **automatically generated** by GitHub based on the merged pull requests and commit history.

- The format and content of these release notes can be customized by editing the `.github/release.yml` file.
- For more information on customizing release notes, refer to [GitHub’s documentation on automatically generated release notes](https://docs.github.com/en/repositories/releasing-projects-on-github/automatically-generated-release-notes).
