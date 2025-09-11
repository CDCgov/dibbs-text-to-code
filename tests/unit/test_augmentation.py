import pytest

from data_curation import augmentation


@pytest.mark.parametrize(
    "text, max_perms, expected",
    [
        # Empty string
        ("", 3, ""),
        # Single word
        ("Blood", 3, "Blood"),
        # Multiple words with special characters
        (
            "SARS-CoV-2 E gene Resp Ql NAA+probe",
            5,
            "E gene Resp SARS-CoV-2 Ql NAA+probe",
        ),
        # More deletions than words
        ("B pert Spt Ql Cult", 10, "Spt pert B Ql Cult"),
    ],
)
class TestScrambleWordOrder:
    def test_scramble_word_order(self, text, max_perms, expected):
        result = augmentation.scramble_word_order(text, max_perms=max_perms)
        assert result == expected


@pytest.mark.parametrize(
    "text, loinc_names, max_inserts,expected ",
    [
        # Empty string
        ("", ["Blood", "Erythrocytes", "Calculation", "CalcRBC", "Volume fraction"], 3, ""),
        # Single word
        (
            "Blood",
            ["Blood", "Erythrocytes", "Calculation", "CalcRBC", "Volume fraction"],
            3,
            "Erythrocytes Blood Volume fraction",
        ),
        # No LOINC names
        ("Hematocrit of Blood", [], 3, "Hematocrit of Blood"),
        # More inserts than LOINC names
        (
            "Hematocrit [Volume Fraction] of Blood by calculation",
            ["Blood", "Erythrocytes", "Calculation", "CalcRBC", "Volume fraction"],
            5,
            "Erythrocytes Hematocrit [Volume Fraction] of Volume fraction Blood by calculation",
        ),
    ],
)
class TestInsertLoincRelatedNames:
    def test_insert_loinc_related_names(self, text, loinc_names, max_inserts, expected):
        result = augmentation.insert_loinc_related_names(
            text, loinc_names, min_inserts=2, max_inserts=max_inserts
        )
        assert result == expected
