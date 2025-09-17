import typing

import utils.regex_patterns as rp


def normalize_text(text: str) -> str:
    """
    Normalize text for comparison by removing non-alphanumeric characters,
    converting to lowercase, and removing all trailing, leading, and excess whitespace.
    :param text: The input text to normalize.
    :return: The normalized text.
    """
    text = rp.ALPHA_NUMERIC.sub(" ", text)

    return " ".join(text.strip().lower().split())


# TODO: Add pydantic models for type checking
def merge_enhancements(
    *dicts: typing.Dict[str, typing.Dict[str, typing.Any]],
) -> typing.Dict[str, typing.Dict[str, typing.Any]]:
    """
     Merge multiple typing.Dictionaries of LOINC enhancements into a single typing.Dictionary.
    Merges 'abbr' and 'replacement' lists, preserves order and uniqueness,
    keeps the first-seen 'code' for each key.
    :param typing.Dicts: Variable number of typing.Dictionaries to merge.
    :return: A single typing.Dictionary with merged enhancements.
    """

    merged: typing.Dict[str, typing.Dict[str, typing.Any]] = {}

    for d in dicts:
        for key, value in d.items():
            code = value["code"]
            abbrs = value.get("abbr", [])
            replacements = value.get("replacement", [])

            if key not in merged:
                merged[key] = {
                    "code": code,
                    "abbr": [],
                    "replacement": [],
                }
            # Keep first-seen code
            if merged[key]["code"] is None and code is not None:
                merged[key]["code"] = code

            # Merge and deduplicate abbrs while preserving order
            merged[key]["abbr"] = merge_two_lists(merged[key]["abbr"], abbrs)

            # Merge and deduplicate replacements while preserving order
            merged[key]["replacement"] = merge_two_lists(merged[key]["replacement"], replacements)

    return merged


def merge_two_lists(
    existing: typing.List[typing.Any], new: typing.List[typing.Any]
) -> typing.List[typing.Any]:
    """
    Merge two lists while preserving order and uniqueness.
    :param list1: The first list.
    :param list2: The second list.
    :return: A merged list with unique elements in order of first appearance.
    """

    return existing + [v for v in new if v not in existing]
