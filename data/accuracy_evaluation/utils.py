import json


def import_json(file_path: str) -> dict | list:
    """
    Imports a JSON / JSONL file and returns its content as a dict or list of dicts.
    :param file_path: Path to the JSON file.
    """
    # Try normal JSON first
    with open(file_path, "r") as f:
        content = f.read().strip()

    # Try parsing full JSON
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        pass

    # If full JSON fails, fall back to JSONL detection
    lines = content.splitlines()
    jsonl_items = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        jsonl_items.append(json.loads(line))


def export_json(dictionary: dict, file_path: str, jsonl: bool = False):
    """
    Exports a dictionary to a JSON file.
    :param dictionary: Dictionary to save.
    :param filename: Output filename.
    """
    with open(file_path, "w") as f:
        json.dump(dictionary, f, indent=2)
