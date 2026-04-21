import glob
import json
from pathlib import Path


def code_root() -> Path:
    """Returns the root directory of the aws_lambda source code."""
    root = Path(__file__).resolve()
    while root.name != "dibbs-text-to-code":
        if root.parent == root:
            raise FileNotFoundError("aws_lambda project root not found.")
        root = root.parent
    return root


def repo_root(start: Path | None = None) -> Path | None:
    """Returns the root directory of the aws_lambda repository, or None if not found."""
    start = start or Path(__file__).resolve()
    for directory in [start, *list(start.parents)]:
        if (directory / "pyproject.toml").is_file():
            return directory
    return None


def read_json(path: str | Path) -> dict:
    """Loads a JSON file."""
    if not Path(path).is_absolute():
        # if path is relative, append to the project root
        path = str(Path(code_root(), path))
    with open(path) as fobj:
        return json.load(fobj)


def load_loinc_enhancements(cwd: str) -> dict:
    """Loads LOINC enhancements from JSON files.

    :param cwd: The current working file directory.
    :return: A dictionary of LOINC enhancements.
    """
    cwd_path = Path(cwd)
    parts = cwd_path.parts

    # Find where "dibbs-text-to-code" appears in the path
    base_idx = -1
    for i, part in enumerate(parts):
        if part == "dibbs-text-to-code":
            # NOTE: DO NOT add a break after this statement
            # The github runner working directory for file management
            # has MULTIPLE directories named "dibbs-text-to-code".
            # We need the LAST one in the path.
            base_idx = i

    if base_idx == -1:
        raise ValueError("Could not find 'dibbs-text-to-code' in current working directory path.")

    # Compute how many levels up we need to go to reach the project root
    levels = (len(parts) - 1) - base_idx
    level_prefix = Path(*([".."] * levels)) if levels > 0 else Path(".")

    # Use glob pattern relative to the computed prefix
    pattern = str(level_prefix / "data" / "snoinc_extracts" / "*_abbrv_syn_*.json")
    matches = glob.glob(pattern)

    enhancements = {}
    # Sorting the paths to ensure consistent loading order for reproducibility, even if the underlying filesystem returns them in a different order. This is only important so that the test are deterministic. The more correct solution would be to mock `random.choice` in the tests, but this is significantly easier with no overhead.
    for match in sorted(matches):
        match_path = Path(match)
        match_path = Path(*match_path.parts[levels:])
        m = read_json(match_path)
        enhancements.update(m)
    return enhancements
