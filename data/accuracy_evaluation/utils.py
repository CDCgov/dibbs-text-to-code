import json


def import_json(file_path: str) -> dict:
    """
    Imports a JSON file and returns its content as a dictionary.
    :param file_path: Path to the JSON file.
    """
    with open(file_path, "r") as f:
        data = json.load(f)
    return data


def export_json(dictionary: dict, file_path: str):
    """
    Exports a dictionary to a JSON file.
    :param dictionary: Dictionary to save.
    :param filename: Output filename.
    """
    with open(file_path, "w") as f:
        json.dump(dictionary, f, indent=2)
