"""Fail if any external GitHub Action under `.github/workflows/` is not pinned to a 40-char commit SHA.

Mitigates supply-chain attacks where a third party re-points a mutable tag (e.g. `v4`)
at a malicious commit. Internal references (`./.github/workflows/...`) are allowed
since they live in this repo.

Run via pre-commit. Exits non-zero on any unpinned external `uses:` line.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

WORKFLOW_DIR = Path(".github/workflows")
USES_RE = re.compile(r'^\s*(?:-\s+)?uses:\s+["\']?(?P<ref>[^"\'\s#]+)["\']?')
SHA_RE = re.compile(r"^[0-9a-f]{40}$")


def find_violations() -> list[tuple[Path, int, str]]:
    """Return `(path, lineno, ref)` for each unpinned external `uses:` reference."""
    violations: list[tuple[Path, int, str]] = []
    for path in sorted(WORKFLOW_DIR.glob("*.y*ml")):
        for lineno, line in enumerate(path.read_text().splitlines(), start=1):
            m = USES_RE.match(line)
            if not m:
                continue
            ref = m.group("ref")
            if ref.startswith("./"):
                continue
            if "@" not in ref:
                violations.append((path, lineno, ref))
                continue
            _, _, version = ref.partition("@")
            if not SHA_RE.match(version):
                violations.append((path, lineno, ref))
    return violations


def main() -> int:
    """Print any violations to stderr and return a non-zero exit code if found."""
    violations = find_violations()
    if not violations:
        return 0
    print("Unpinned GitHub Action references found:", file=sys.stderr)
    for path, lineno, ref in violations:
        print(f"  {path}:{lineno}: {ref}", file=sys.stderr)
    print(
        "\nPin each external `uses:` to a 40-char commit SHA with a version "
        "comment, e.g.:\n"
        "  uses: actions/checkout@de0fac2e4500dabe0009e67214ff5f5447ce83dd # v6.0.2\n"
        "Tip: `pinact run` (https://github.com/suzuki-shunsuke/pinact) "
        "resolves tags to SHAs automatically.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
