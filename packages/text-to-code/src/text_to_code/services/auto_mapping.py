from text_to_code.services.auto_mapping_dict import AUTO_MAPPING


def convert_known_code(nonstandard_input: str) -> str:
    """Convert a known nonstandard input to its standardized value.

    :param nonstandard_input: The nonstandard input string to convert.
    :returns: The standardized value when a known mapping exists, otherwise the
        original input string.
    """
    if nonstandard_input in AUTO_MAPPING:
        return AUTO_MAPPING[nonstandard_input]

    return nonstandard_input
