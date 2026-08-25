import functools
import json
from pathlib import Path


@functools.cache
def get_auto_mapping() -> dict[str, str]:
    """Load and invert the auto-mapping dictionary.

    :returns: A mapping of nonstandard input strings to standardized values.
    """
    mapping_path = Path(__file__).resolve().parent.parent / "data" / "auto_mapping.json"

    with mapping_path.open(encoding="utf-8") as mapping_file:
        code_to_inputs: dict[str, list[str]] = json.load(mapping_file)

    inputs_to_codes: dict[str, str] = {}
    for code, inputs in code_to_inputs.items():
        for i in inputs:
            inputs_to_codes[i] = code

    return inputs_to_codes


def convert_known_code(nonstandard_input: str) -> str:
    """Convert a known nonstandard input to its standardized value.

    :param nonstandard_input: The nonstandard input string to convert.
    :returns: The standardized value when a known mapping exists, otherwise the
        original input string.
    """
    known_inputs_to_codes = get_auto_mapping()

    if nonstandard_input in known_inputs_to_codes:
        return known_inputs_to_codes[nonstandard_input]

    return nonstandard_input
