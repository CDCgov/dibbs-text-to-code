from typing import Any


# TODO: Add pydantic models for type checking
def merge_enhancements(
    *dicts: dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    """Merge multiple dictionaries of LOINC enhancements into a single dictionary.

    Merges 'abbrv' and 'synonyms' lists, preserves order and uniqueness,
    keeps the first-seen 'code' for each key.
    :param Dicts: Variable number of dictionaries to merge.
    :return: A single dictionary with merged enhancements.
    """
    merged: dict[str, dict[str, Any]] = {}

    for d in dicts:
        for _key, value in d.items():
            key = _key.lower()
            code = value["code"]
            # We want the key to be lowercase, but not the values--this way, we
            # can always search regardless of the input formatting, but we'll
            # get back something already LOINC-capitalization expected
            abbrvs = list(value.get("abbrv", []))
            synonyms = list(value.get("synonyms", []))

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


def merge_two_lists(existing: list[Any], new: list[Any]) -> list[Any]:
    """Merge two lists while preserving order and uniqueness.

    :param list1: The first list.
    :param list2: The second list.
    :return: A merged list with unique elements in order of first appearance.
    """
    return existing + [v for v in new if v not in existing]
