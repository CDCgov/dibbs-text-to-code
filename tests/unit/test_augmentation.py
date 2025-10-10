import csv
import os
import sys

import pytest

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from data_curation import augmentation
from data_curation.configs import AUGMENTATION_WITHOUT_ENHANCEMENT
from utils import normalize
from utils import path

enhancements = path.load_loinc_enhancements(os.getcwd())
LOINC_ENHANCEMENTS = normalize.merge_enhancements(enhancements)
assert len(LOINC_ENHANCEMENTS) > 0


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
        expected_result = "Thi term is intnded to collate similar measurements for the LOINC SNOMED CT Collaboration i a ontological view. Addtionally i can be used to communicate a laboraory order, either alone or in combinaion with specimen or other information in the odr. It may NOT be sed to report back the measured patient value."
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
    "text, loinc_names, max_inserts, expected",
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


class TestGenerateDisjointIntervals:
    def test_generate_disjoint_intervals(self):
        # Test case 1: already disjoint intervals
        words = [("blood", (0, 0)), ("glucose", (1, 1)), ("measurement", (2, 2))]
        filtered = augmentation._generate_disjoint_intervals(words)
        assert filtered == [("blood", (0, 0)), ("glucose", (1, 1)), ("measurement", (2, 2))]

        # Test case 2: empty list
        filtered = augmentation._generate_disjoint_intervals([])
        assert filtered == []

        # Test case 3: overlap with a singleton and interval
        words = [
            ("dog+cat+horse epithelilal allergen dander", (0, 3)),
            ("allergen dander", (2, 3)),
            ("dog+cat+horse", (0, 0)),
        ]
        filtered = augmentation._generate_disjoint_intervals(words)
        assert filtered == [("dog+cat+horse", (0, 0)), ("allergen dander", (2, 3))]


class TestFilterCandidatesForEnhancement:
    def test_filter_candidates_for_enhancement(self):
        # Case 1: Empty list
        assert augmentation._filter_candidates_for_enhancement([], LOINC_ENHANCEMENTS) == []

        # Case 2: Some disjoint candidates, some of which have enhancements
        words = [("epidermal", (0, 0)), ("IgE", (1, 1)), ("Serum", (2, 2)), ("dander+Cat", (3, 3))]
        filtered = augmentation._filter_candidates_for_enhancement(words, LOINC_ENHANCEMENTS)
        assert filtered == [("IgE", (1, 1))]

        # Case 3: Substring candidates with enhancement
        words = [
            ("Allergen Mix", (0, 1)),
            ("IgE", (2, 2)),
            ("Serum", (3, 3)),
            ("(Dog dander+Cat epithelium+Horse dander)", (4, 7)),
        ]
        filtered = augmentation._filter_candidates_for_enhancement(words, LOINC_ENHANCEMENTS)
        assert filtered == [("IgE", (2, 2)), ("(Dog dander+Cat epithelium+Horse dander)", (4, 7))]

        # Case 3: Candidate list with no tokens that have enhancements
        words = [("there", (0, 0)), ("are", (1, 1)), ("no", (2, 2)), ("enhancements", (3, 3))]
        filtered = augmentation._filter_candidates_for_enhancement(words, LOINC_ENHANCEMENTS)
        assert filtered == []


@pytest.mark.parametrize(
    "words, expected",
    [
        # Test case 1: Typical case with multiple words
        (
            [("blood", (0, 0)), ("glucose", (1, 1)), ("measurement", (2, 2))],
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
        ([("blood", (0, 0))], [("blood", (0, 0))]),
        # # Test case 3: Two words
        (
            [("blood", (0, 0)), ("glucose", (1, 1))],
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
        result = augmentation._generate_enhancement_candidates(words)
        assert result == expected


class TestEnhanceLoinc:
    def test_enhance_loinc(self):
        # Case 1: sanity check empty string
        assert augmentation.enhance_loinc_str("", "all", 5) == ""

        # Case 2: One enhancement that's a disjoint singleton, and its replacement
        # is multiple words--make sure the rest of the string is unaffected
        code_str = "Weed Allergen Mix 3 (Mugwort+Goosefoot or Lambs quarters+English plantain+Goldenrod+Nettle) IgE Ab [Measurement] in Serum"  # noqa
        enhanced_code = augmentation.enhance_loinc_str(code_str, "all", 5)
        assert (
            enhanced_code
            == "Weed Allergen Mix 3 (Mugwort+Goosefoot or Lambs quarters+English plantain+Goldenrod+Nettle) immune globulin e Ab [Measurement] in Serum"
        )  # noqa

        # Case 3: Multiple enhancements, one singleton and one substring
        # The substring's replacement is shorter, so this test's string
        # truncation and the deletion of other tokens later.
        # Make sure word is modified in reverse order and both take effect
        code_str = "Epidermal Allergen Mix (Dog dander+Cat epithelium+Horse dander) Ab.IgE [Measurement] panel - Urine"  # noqa
        enhanced_code = augmentation.enhance_loinc_str(code_str, "all", 5, min_enhancements=2)
        assert (
            enhanced_code
            == "Epidermal Allergen Mix epid allerg mix Ab.IgE [Measurement] panel - ur"
        )  # noqa


class TestEnhanceLoincError:
    def test_enhance_loinc_str_raise_error(self):
        text = "Blood Glucose Measurement"

        with pytest.raises(ValueError):
            augmentation.enhance_loinc_str(
                text=text,
                enhancement_type="abbrv",
                max_enhancements=1,
                min_enhancements=3,
            )


@pytest.mark.parametrize(
    "text, related_names, num_examples, config, expected",
    [
        # Augmentation without any enhancements
        (
            "Hematocrit [Volume Fraction] of Blood by calculation",
            [
                "Blood",
                "Erythrocytes",
                "Calculation",
                "CalcRBC",
                "Volume fraction",
                "% mL",
                "Hemat.",
                "HoBBC",
            ],
            3,
            AUGMENTATION_WITHOUT_ENHANCEMENT,
            [
                "CalcRC [Volume Fraction] of by Hematocrit Blood calculation",
                "CalcRBC Hematorit Fraction] HBBC of Blood by [Voume Volume fraction calculation",
                "Hematocrit [Volume Fraction] of Blood % mL by calculation",
            ],
        ),
    ],
)
class TestGenerateAugmentedTrainingSamples:
    def test_generate_augmented_examples(self, text, related_names, num_examples, config, expected):
        result = augmentation.generate_augmented_examples(text, related_names, num_examples, config)
        assert result == expected


class TestBuildAugmentedLoincFiles:
    def test_build_augmented_loinc_files(self, cleanup_tmp_files):
        working_dir = os.getcwd()
        if working_dir.split("/")[-1] == "unit":
            input_path = "assets/loinc_lab_names_20250930.csv"
        elif working_dir.split("/")[-1] == "dibbs-text-to-code":
            input_path = "./tests/unit/assets/loinc_lab_names_20250930.csv"
        num_sn = 2
        num_lcn = 2
        num_dn = 2
        config = {
            "long_common_name": AUGMENTATION_WITHOUT_ENHANCEMENT,
            "short_name": AUGMENTATION_WITHOUT_ENHANCEMENT,
            "display_name": AUGMENTATION_WITHOUT_ENHANCEMENT,
        }
        output_base_path = "./tmp/augmented_loinc"
        augmentation.build_augmented_loinc_files(
            input_path=input_path,
            config=config,
            num_sn=num_sn,
            num_lcn=num_lcn,
            num_dn=num_dn,
            output_path_base=output_base_path,
        )

        # Check that the expected files were created
        # Assert files were created
        for key in config:
            file_path = f"{output_base_path}_{key}.csv"
            assert os.path.exists(file_path)

            # Check that the files are not empty
            assert os.path.getsize(file_path) > 0

            # Check that the files contain the expected number of augmented examples
            with open(file_path, "r", encoding="utf-8", newline="") as fp:
                reader = csv.reader(fp, delimiter=":")
                for row in reader:
                    loinc_code, base_value, augmented_examples = row
                    augmented_examples = augmented_examples.split("|")
                    if key == "long_common_name":
                        assert len(augmented_examples) == num_lcn
                    elif key == "short_name":
                        assert len(augmented_examples) == num_sn
                    elif key == "display_name":
                        assert len(augmented_examples) == num_dn
