import os
import sys

import pytest

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from data_emulation import loinc_enhancement
from utils import normalize, path

enhancements = path.load_loinc_enhancements(os.getcwd())
LOINC_ENHANCEMENTS = normalize.merge_enhancements(enhancements)
assert len(LOINC_ENHANCEMENTS) > 0


class TestGenerateDisjointIntervals:
    def test_generate_disjoint_intervals(self):
        """Test generate disjoint internals with 3 test cases.

        Test cases:
        1) already disjoint intervals
        2) empty list
        3) overlap with a singleton and interval
        """
        # Test case 1: already disjoint intervals
        words = [("blood", (0, 0)), ("glucose", (1, 1)), ("measurement", (2, 2))]
        filtered = loinc_enhancement._generate_disjoint_intervals(words)
        assert filtered == [("blood", (0, 0)), ("glucose", (1, 1)), ("measurement", (2, 2))]

        # Test case 2: empty list
        filtered = loinc_enhancement._generate_disjoint_intervals([])
        assert filtered == []

        # Test case 3: overlap with a singleton and interval
        words = [
            ("dog+cat+horse epithelilal allergen dander", (0, 3)),
            ("allergen dander", (2, 3)),
            ("dog+cat+horse", (0, 0)),
        ]
        filtered = loinc_enhancement._generate_disjoint_intervals(words)
        assert filtered == [("dog+cat+horse", (0, 0)), ("allergen dander", (2, 3))]


class TestFilterCandidatesForEnhancement:
    def test_filter_candidates_for_enhancement(self):
        """Test filter candidates for enhancements."""
        # Case 1: Empty list
        assert loinc_enhancement._filter_candidates_for_enhancement([], LOINC_ENHANCEMENTS) == []

        # Case 2: Some disjoint candidates, some of which have enhancements
        words = [("epidermal", (0, 0)), ("IgE", (1, 1)), ("Serum", (2, 2)), ("dander+Cat", (3, 3))]
        filtered = loinc_enhancement._filter_candidates_for_enhancement(words, LOINC_ENHANCEMENTS)
        assert filtered == [("IgE", (1, 1))]

        # Case 3: Substring candidates with enhancement
        words = [
            ("Allergen Mix", (0, 1)),
            ("IgE", (2, 2)),
            ("Serum", (3, 3)),
            ("(Dog dander+Cat epithelium+Horse dander)", (4, 7)),
        ]
        filtered = loinc_enhancement._filter_candidates_for_enhancement(words, LOINC_ENHANCEMENTS)
        assert filtered == [("IgE", (2, 2)), ("(Dog dander+Cat epithelium+Horse dander)", (4, 7))]

        # Case 3: Candidate list with no tokens that have enhancements
        words = [("there", (0, 0)), ("are", (1, 1)), ("no", (2, 2)), ("enhancements", (3, 3))]
        filtered = loinc_enhancement._filter_candidates_for_enhancement(words, LOINC_ENHANCEMENTS)
        assert filtered == []


@pytest.mark.parametrize(
    ("words", "expected"),
    [
        # Test case 1: Typical case with multiple words
        (
            [("blood", [0]), ("glucose", [1]), ("measurement", [2])],
            [
                ("blood", (0, 0)),
                ("glucose", (1, 1)),
                ("measurement", (2, 2)),
                ("blood glucose", (0, 1)),
                ("blood glucose measurement", (0, 2)),
                ("glucose measurement", (1, 2)),
            ],
        ),
        # Test case 2: Single word (no substrings possible, just base word)
        ([("blood", [0])], [("blood", (0, 0))]),
        # # Test case 3: Two words
        (
            [("blood", [0]), ("glucose", [1])],
            [
                ("blood", (0, 0)),
                ("glucose", (1, 1)),
                ("blood glucose", (0, 1)),
            ],
        ),
    ],
)
class TestGenerateEnhancementCandidates:
    def test_generate_enhancement_candidates(self, words, expected):
        """Test generate enhancement candidates."""
        result = loinc_enhancement._generate_enhancement_candidates(words)
        assert result == expected


class TestEnhanceLoinc:
    def test_enhance_loinc(self):
        """Test enhance LOINC."""
        # Case 1: sanity check empty string
        assert loinc_enhancement.enhance_loinc_str("", "all", 5) == ""

        # Case 2: One enhancement that's a disjoint singleton, and its replacement
        # is multiple words--make sure the rest of the string is unaffected
        code_str = "Weed Allergen Mix 3 (Mugwort+Goosefoot or Lambs quarters+English plantain+Goldenrod+Nettle) IgE Ab [Measurement] in Serum"
        enhanced_code = loinc_enhancement.enhance_loinc_str(code_str, "all", 5)
        assert (
            enhanced_code
            == "Weed Allergen Mix 3 (Mugwort+Goosefoot or Lambs quarters+English plantain+Goldenrod+Nettle) Immunoglobulin E Ab [Measurement] in Serum"
        )

        # Case 3: Multiple enhancements, one singleton and one substring
        # The substring's replacement is shorter, so this test's string
        # truncation and the deletion of other tokens later.
        # Make sure word is modified in reverse order and both take effect
        code_str = "Epidermal Allergen Mix (Dog dander+Cat epithelium+Horse dander) Ab.IgE [Measurement] panel - Urine"
        enhanced_code = loinc_enhancement.enhance_loinc_str(code_str, "all", 5, min_enhancements=2)
        assert enhanced_code == "Epidermal Allergen Mix Dander Ab.IgE [Measurement] panel - Urn"

    def test_enhance_loinc_str_skips_candidate_without_requested_enhancement_type(
        self, monkeypatch
    ):
        monkeypatch.setattr(
            loinc_enhancement,
            "LOINC_ENHANCEMENTS",
            {
                "blood": {
                    "synonyms": ["serum"],
                }
            },
        )

        result = loinc_enhancement.enhance_loinc_str("Blood", "abbrv", 1)

        assert result == "Blood"


class TestEnhanceLoincError:
    def test_enhance_loinc_str_raise_error(self):
        """Test enhance LOINC string with error."""
        text = "Blood Glucose Measurement"

        with pytest.raises(
            ValueError, match="max_enhancements must be greater than min_enhancements"
        ):
            loinc_enhancement.enhance_loinc_str(
                text=text,
                enhancement_type="abbrv",
                max_enhancements=1,
                min_enhancements=3,
            )
