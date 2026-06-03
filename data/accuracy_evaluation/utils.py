import json


def import_json(file_path: str) -> dict:
    """
    Imports a JSON / JSONL file and returns its content as a dict or list of dicts.
    
    :param file_path: Path to the JSON file.
    """
    with open(file_path, "r") as f:
        content = f.read().strip()

    parsed_json = json.loads(content)

    if not isinstance(parsed_json, dict):
        raise ValueError(f"Expected JSON object in {file_path}")

    return parsed_json


def export_json(dictionary: dict | list, file_path: str, jsonl: bool = False) -> None:
    """
    Exports a dictionary to a JSON file.
    
    :param dictionary: Dictionary to save.
    :param filename: Output filename.
    """
    with open(file_path, "w") as f:
        json.dump(dictionary, f, indent=2)
