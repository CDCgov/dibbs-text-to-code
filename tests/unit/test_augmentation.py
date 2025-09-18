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


class TestCharDeletion:
    LOINC_LAB_TEXT_1 = "5-Hydroxytryptophan [Measurement] in Urine"
    LOINC_LAB_TEXT_2 = "6-oxo-piperidine-2-carboxylate and 6(R+S)-oxo-propylpiperidine-2-carboxylate panel - Urine and Serum or Plasma"
    LOINC_LAB_TEXT_3 = "This term is intended to collate similar measurements for the LOINC SNOMED CT Collaboration in an ontological view. Additionally, it can be used to communicate a laboratory order, either alone or in combination with specimen or other information in the order. It may NOT be used to report back the measured patient value."

    def test_random_deletion_bad_method(self):
        result = augmentation.random_char_deletion(self.LOINC_LAB_TEXT_3, 1, 10, 2, "test")
        assert result == self.LOINC_LAB_TEXT_3

    def test_random_char_deletion(self):
        test_string = self.LOINC_LAB_TEXT_1
        expected_result = "5Hydroytryptophan [Measureent] n rie"
        result = augmentation.random_char_deletion(test_string, 3, 8, 2, "char")
        assert len(result) < len(test_string)
        assert result == expected_result

        test_string = self.LOINC_LAB_TEXT_3
        expected_result = "This term is intnded to collate similar measurements fr he OINC SNOMED CT Collaboration in an ontological view. Addtionally, it can be used to communicate a laboraory order, either alone or in combiaion with specimen or oter information in the odr. It may NOT be sed to report back the measured patient value."
        result = augmentation.random_char_deletion(test_string, 3, 15, 4, "char")
        assert len(result) < len(test_string)
        assert result == expected_result

    def test_random_char_deletion_word(self):
        test_string = self.LOINC_LAB_TEXT_2
        expected_result = "6-oxo-piperidine-2-carbxylate and 6(R+S)-oxo-propylpiperidine-2-carboxylate panel  Urine and Serum or Plasma"
        result = augmentation.random_char_deletion(test_string, 1, 10, 3, "word")
        assert len(test_string) == len(result) + 2
        assert result == expected_result


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


class TestEnhanceWithLoincAbbreviations:
    def test_enhance_loinc_str_abbreviation(self):
        # Test case 1: Basic enhancement with a single synonym
        text = "Blood Glucose Measurement"
        expected = "blood glucoseur measurement"
        result = augmentation.enhance_loinc_str(
            text,
            enhancement_type="synonyms",
            max_enhancements=2,
            min_enhancements=1,
        )
        assert result == expected

    def test_enhance_loinc_str_abbreviation_multiple(self):
        # Test case 2: Enhancement with "all" replacements
        text = "Blood Glucose Measurement"
        expected = "blood gluc measurement"
        result = augmentation.enhance_loinc_str(
            text,
            enhancement_type="all",
            max_enhancements=2,
            min_enhancements=1,
        )
        assert result == expected

    def test_enhance_loinc_str_raise_error(self):
        # Test case 3: Invalid enhancement numbers
        text = "Blood Glucose Measurement"

        with pytest.raises(ValueError):
            augmentation.enhance_loinc_str(
                text,
                enhancement_type="abbrv",
                max_enhancements=1,
                min_enhancements=3,
            )

    def test_enhance_loinc_str_no_enhancements(self):
        # Test case 4: No possible enhancements
        text = "This term has no enhancements"

        result = augmentation.enhance_loinc_str(
            text,
            enhancement_type="abbrv",
            max_enhancements=2,
            min_enhancements=1,
        )
        assert result == text
