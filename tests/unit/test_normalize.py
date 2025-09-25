import pytest

from utils import normalize as utils


@pytest.mark.parametrize(
    "text, expected",
    [
        # Removes special characters and extra spaces, converts to lowercase
        (
            " Cell growth [Presence] of Amniocytes Qualitative by Tissue culture",
            "cell growth presence of amniocytes qualitative by tissue culture",
        ),
        # Replaces special characters with spaces
        (
            "Power spectrum.theta frequency/Power spectrum.total",
            "power spectrum theta frequency power spectrum total",
        ),
        (
            "Platelet aggregation.ristocetin induced^125 ug/mL",
            "platelet aggregation ristocetin induced 125 ug ml",
        ),
    ],
)
class TestNormalizeText:
    def test_normalize_text(self, text, expected):
        assert utils.normalize_text(text) == expected


@pytest.mark.parametrize(
    "existing, new, expected",
    [
        # Merges two lists with some overlap, preserving order and uniqueness
        (["a", "b", "c"], ["b", "c", "d"], ["a", "b", "c", "d"]),
        # Merges two lists with no overlap
        (["a", "b", "c"], ["d", "e", "f"], ["a", "b", "c", "d", "e", "f"]),
        # Merges when one list is empty
        ([], ["a", "b", "c"], ["a", "b", "c"]),
        # Merges two identical lists
        (["a", "b", "c"], ["a", "b", "c"], ["a", "b", "c"]),
    ],
)
class TestMergeTwoLists:
    def test_merge_two_lists(self, existing, new, expected):
        merged = utils.merge_two_lists(existing, new)
        assert merged == expected


@pytest.mark.parametrize(
    "dict1, dict2, expected",
    [
        # Merges two dicts with some overlap, preserving order and uniqueness
        (
            {
                "EntSub": {"code": "LP100323-7", "abbrv": [], "synonyms": ["Entitic substance"]},
                "ClockTime": {"code": "LP101588-4", "abbrv": ["Clock time"], "synonyms": []},
                "EngRatFr": {"code": "LP101814-4", "abbrv": [], "synonyms": ["hello"]},
            },
            {
                "EngRatFr": {
                    "code": "LP101814-4",
                    "abbrv": [],
                    "synonyms": ["hello", "goodbye"],
                },
                "PPresDiff": {"code": "LP101909-2", "abbrv": [], "synonyms": []},
                "VFrDiff": {"code": "LP101984-5", "abbrv": [], "synonyms": []},
            },
            {
                "entsub": {"code": "LP100323-7", "abbrv": [], "synonyms": ["entitic substance"]},
                "clocktime": {"code": "LP101588-4", "abbrv": ["clock time"], "synonyms": []},
                "engratfr": {"code": "LP101814-4", "abbrv": [], "synonyms": ["hello", "goodbye"]},
                "ppresdiff": {"code": "LP101909-2", "abbrv": [], "synonyms": []},
                "vfrdiff": {"code": "LP101984-5", "abbrv": [], "synonyms": []},
            },
        ),
        # Merges two dicts with no overlap
        (
            {
                "EntSub": {"code": "LP100323-7", "abbrv": [], "synonyms": ["Entitic substance"]},
                "ClockTime": {"code": "LP101588-4", "abbrv": ["Clock time"], "synonyms": []},
                "EngRatFr": {"code": "LP101814-4", "abbrv": [], "synonyms": ["hello"]},
            },
            {
                "TscoreDiff": {
                    "code": "LP202986-8",
                    "abbrv": [],
                    "synonyms": ["T-score", "Score difference"],
                },
            },
            {
                "entsub": {"code": "LP100323-7", "abbrv": [], "synonyms": ["entitic substance"]},
                "clocktime": {"code": "LP101588-4", "abbrv": ["clock time"], "synonyms": []},
                "engratfr": {"code": "LP101814-4", "abbrv": [], "synonyms": ["hello"]},
                "tscorediff": {
                    "code": "LP202986-8",
                    "abbrv": [],
                    "synonyms": ["t-score", "score difference"],
                },
            },
        ),
        # Merges when one dict is empty
        (
            {},
            {
                "EntSub": {"code": "LP100323-7", "abbrv": [], "synonyms": ["Entitic substance"]},
                "ClockTime": {"code": "LP101588-4", "abbrv": ["Clock time"], "synonyms": []},
                "EngRatFr": {"code": "LP101814-4", "abbrv": [], "synonyms": ["hello"]},
            },
            {
                "entsub": {"code": "LP100323-7", "abbrv": [], "synonyms": ["entitic substance"]},
                "clocktime": {"code": "LP101588-4", "abbrv": ["clock time"], "synonyms": []},
                "engratfr": {"code": "LP101814-4", "abbrv": [], "synonyms": ["hello"]},
            },
        ),
        # Merges two identical dicts
        (
            {
                "EntSub": {"code": "LP100323-7", "abbrv": [], "synonyms": ["Entitic substance"]},
                "ClockTime": {"code": "LP101588-4", "abbrv": ["Clock time"], "synonyms": []},
                "EngRatFr": {"code": "LP101814-4", "abbrv": [], "synonyms": ["hello"]},
            },
            {
                "EntSub": {"code": "LP100323-7", "abbrv": [], "synonyms": ["Entitic substance"]},
                "ClockTime": {"code": "LP101588-4", "abbrv": ["Clock time"], "synonyms": []},
                "EngRatFr": {"code": "LP101814-4", "abbrv": [], "synonyms": ["hello"]},
            },
            {
                "entsub": {"code": "LP100323-7", "abbrv": [], "synonyms": ["entitic substance"]},
                "clocktime": {"code": "LP101588-4", "abbrv": ["clock time"], "synonyms": []},
                "engratfr": {"code": "LP101814-4", "abbrv": [], "synonyms": ["hello"]},
            },
        ),
    ],
)
class TestMergeEnhancements:
    def test_merge_enhancements(self, dict1, dict2, expected):
        merged = utils.merge_enhancements(dict1, dict2)
        assert merged == expected
