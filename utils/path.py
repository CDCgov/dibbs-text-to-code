import glob
import json
import pathlib


def code_root() -> pathlib.Path:
    """
    Returns the root directory of the dibbs_text_to_code source code.
    """
    root = pathlib.Path(__file__).resolve()
    while root.name != "dibbs-text-to-code":
        if root.parent == root:
            raise FileNotFoundError("dibbs_text_to_code project root not found.")
        root = root.parent
    return root


def repo_root(start: pathlib.Path | None = None) -> pathlib.Path | None:
    """
    Returns the root directory of the dibbs_text_to_code repository, or None if not found.
    """
    start = start or pathlib.Path(__file__).resolve()
    for directory in [start] + list(start.parents):
        if (directory / "pyproject.toml").is_file():
            return directory
    return None


def read_json(path: str) -> dict:
    """
    Loads a JSON file.
    """
    if not pathlib.Path(path).is_absolute():
        # if path is relative, append to the project root
        path = str(pathlib.Path(code_root(), path))
    with open(path, "r") as fobj:
        return json.load(fobj)


def load_loinc_enhancements(cwd: str):
    """
    Loads LOINC enhancements from JSON files.

    :param cwd: The current working file directory.
    :return: A dictionary of LOINC enhancements.
    """
    # Determine how many levels deep in the call structure we are
    dirs = cwd.split("/")
    base_idx = -1
    for i, dir in enumerate(dirs):
        if dir == "dibbs-text-to-code":
            base_idx = i

    # However many levels deep is how far we need to go back up to hit
    # the data folder
    levels = (len(dirs) - 1) - base_idx
    level_prefix = "../" * levels

    pattern = level_prefix + "data/snoinc_extracts/*_abbrv_syn_*.json"
    matches = glob.glob(pattern)
    enhancements = {}

    for match in matches:
        relative_normalized_match = "/".join(match.split("/")[levels:])
        m = read_json(relative_normalized_match)
        enhancements.update(m)

    return enhancements
