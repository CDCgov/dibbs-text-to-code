import functools
import json
from pathlib import Path


@functools.cache
def get_auto_mapping() -> dict[str, str]:
    """Load the auto-mapping dictionary.

    :returns: A mapping of normalized nonstandard input strings to standardized values.
    """
    mapping_path = Path(__file__).resolve().parent.parent / "data" / "auto_mapping.json"

    with mapping_path.open(encoding="utf-8") as mapping_file:
        inputs_to_codes: dict[str, str] = json.load(mapping_file)

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
