import csv
import os
import pathlib
import sys

import pytest

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from data_curation.configs import AUGMENTATION_WITHOUT_ENHANCEMENT

from data_curation import augmentation
from utils import normalize
from utils import path

enhancements = path.load_loinc_enhancements(os.getcwd())
LOINC_ENHANCEMENTS = normalize.merge_enhancements(enhancements)
assert len(LOINC_ENHANCEMENTS) > 0


class TestCharDeletion:
    LOINC_LAB_TEXT_1 = "5-Hydroxytryptophan [Measurement] in Urine"
    LOINC_LAB_TEXT_2 = "6-oxo-piperidine-2-carboxylate and 6(R+S)-oxo-propylpiperidine-2-carboxylate panel - Urine and Serum or Plasma"
    LOINC_LAB_TEXT_3 = "This term is intended to collate similar measurements for the LOINC SNOMED CT Collaboration in an ontological view. Additionally, it can be used to communicate a laboratory order, either alone or in combination with specimen or other information in the order. It may NOT be used to report back the measured patient value."

    def test_random_deletion_bad_method(self):
        """Test random deletion bad method."""
        result = augmentation.random_char_deletion(self.LOINC_LAB_TEXT_3, 1, 10, 2, "test")
        assert result == self.LOINC_LAB_TEXT_3

    def test_random_char_deletion(self):
        """Test random character deletion."""
        test_string = self.LOINC_LAB_TEXT_1
        expected_result = "5Hydroxytrypophan [Masuremet] in Uine"
        result = augmentation.random_char_deletion(test_string, 3, 8, 2, "char")
        assert len(result) < len(test_string)
        assert result == expected_result

        test_string = self.LOINC_LAB_TEXT_3
        expected_result = "This term is intended to collate similar measuremets for the LOINC SNOMED CT Collaboration in an ontological view. ddtionally, it can be use to communicate a laboratory order, either alone or i combination with specimen or oher information in the rder. It may NOT b used to report back the measured patient vale."
        result = augmentation.random_char_deletion(test_string, 3, 15, 4, "char")
        assert len(result) < len(test_string)
        assert result == expected_result

    def test_random_char_deletion_word(self):
        """Test random char deletion word."""
        test_string = self.LOINC_LAB_TEXT_2
        expected_result = "6-oxo-piperidine-2-carboxylate ad 6(R+S)-oxo-propylpiperidine-2-carboxylate panel - Une n erum or Plasma"
        result = augmentation.random_char_deletion(test_string, 1, 10, 3, "word")
        assert len(test_string) == len(result) + 6
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
            "Volume fraction Blood Blood Erythrocytes",
        ),
        # No LOINC names
        ("Hematocrit of Blood", [], 3, "Hematocrit of Blood"),
        # More inserts than LOINC names
        (
            "Hematocrit [Volume Fraction] of Blood by calculation",
            ["Blood", "Erythrocytes", "Calculation", "CalcRBC", "Volume fraction"],
            5,
            "CalcRBC Hematocrit [Volume Calculation Fraction] Blood of Blood by Erythrocytes calculation",
        ),
    ],
)
class TestInsertLoincRelatedNames:
    def test_insert_loinc_related_names(self, text, loinc_names, max_inserts, expected):
        """Test insert LOINC related names."""
        result = augmentation.insert_loinc_related_names(
            text, loinc_names, min_inserts=2, max_inserts=max_inserts
        )
        assert result == expected


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
                "Hematocrit [Volume Fraction] of Blood by calculation Blood",
                "% Hematocrit mL [Volume Fraction] of Blood by Erythrocytes calculation",
                "Volume fracion % mL Hematocrt Calulation [Volume Fration] of Blood by calculation",
            ],
        ),
    ],
)
class TestGenerateAugmentedTrainingSamples:
    def test_generate_augmented_examples(self, text, related_names, num_examples, config, expected):
        """Test generate augmented examples."""
        result = augmentation.generate_augmented_examples(text, related_names, num_examples, config)
        assert result == expected


class TestBuildAugmentedLoincFiles:
    def test_build_augmented_loinc_files(self, cleanup_tmp_files):
        """Test build augmented LOINC files."""
        working_dir = pathlib.Path.cwd()
        if working_dir.name == "unit":
            input_path = pathlib.Path("assets") / "loinc_lab_names_20250930.csv"
        elif working_dir.name == "dibbs-text-to-code":
            input_path = "packages/data-curation/tests/assets/loinc_lab_names_20250930.csv"
        else:
            raise RuntimeError(f"Unexpected working directory: {working_dir}")
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
