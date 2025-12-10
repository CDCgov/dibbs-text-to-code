import typing

import utils.regex_patterns as rp


def normalize_text(text: str) -> str:
    """Normalize text for comparison by removing non-alphanumeric characters,
    converting to lowercase, and removing all trailing, leading, and excess whitespace.
    :param text: The input text to normalize.
    :return: The normalized text.
    """
    text = rp.ALPHA_NUMERIC.sub(" ", text)

    return " ".join(text.strip().lower().split())


# TODO: Add pydantic models for type checking
def merge_enhancements(
    *dicts: dict[str, dict[str, typing.Any]],
) -> dict[str, dict[str, typing.Any]]:
    """Merge multiple typing.Dictionaries of LOINC enhancements into a single typing.Dictionary.
    Merges 'abbrv' and 'synonyms' lists, preserves order and uniqueness,
    keeps the first-seen 'code' for each key.
    :param typing.Dicts: Variable number of typing.Dictionaries to merge.
    :return: A single typing.Dictionary with merged enhancements.
    """
    merged: dict[str, dict[str, typing.Any]] = {}

    for d in dicts:
        for key, value in d.items():
            key = key.lower()
            code = value["code"]
            abbrvs = [a.lower() for a in value.get("abbrv", [])]
            synonyms = [s.lower() for s in value.get("synonyms", [])]

            if key not in merged:
                merged[key] = {
                    "code": code,
                    "abbrv": [],
                    "synonyms": [],
                }
            # Keep first-seen code
            if merged[key]["code"] is None and code is not None:
                merged[key]["code"] = code

            # Merge and deduplicate abbrvs while preserving order
            merged[key]["abbrv"] = merge_two_lists(merged[key]["abbrv"], abbrvs)

            # Merge and deduplicate synonyms while preserving order
            merged[key]["synonyms"] = merge_two_lists(merged[key]["synonyms"], synonyms)

    return merged


def merge_two_lists(
    existing: list[typing.Any],
    new: list[typing.Any],
) -> list[typing.Any]:
    """Merge two lists while preserving order and uniqueness.
    :param list1: The first list.
    :param list2: The second list.
    :return: A merged list with unique elements in order of first appearance.
    """
    return existing + [v for v in new if v not in existing]
