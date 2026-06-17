import os
import random
import sys
from typing import ClassVar

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from data_curation.data_emulation import post_process
from utils import normalize, path

enhancements = path.load_loinc_enhancements(os.getcwd())
LOINC_ENHANCEMENTS = normalize.merge_enhancements(enhancements)
assert len(LOINC_ENHANCEMENTS) > 0

random.seed(3141)


class TestApplyDeletionPostProcessing:
    def test_one_word_component(self):
        code_str = "Barbiturates [Presence] in Urine by Screen method"
        fsn = "Barbiturates:PrThr:Pt:Urine:Ord:Screen"
        deleted = post_process.apply_deletion_post_processing(
            code_str, fsn=fsn, loinc_enhancements=LOINC_ENHANCEMENTS
        )
        assert deleted == "Barbiturates [Presence] in by Screen"

    def test_multi_word_component(self):
        code_str = "Oxygen saturation in Arterial Blood"
        fsn = "Oxygen saturation:MFr:Pt:BldA:Qn:"
        deleted = post_process.apply_deletion_post_processing(
            code_str, fsn=fsn, loinc_enhancements=LOINC_ENHANCEMENTS
        )
        assert deleted == "Oxygen saturation in Blood"

    def test_full_code_string_is_component(self):
        code_str = "Complete blood count W Auto Differential panel"
        fsn = "Complete blood count W Auto Differential panel:-:Pt:Bld:Qn:"
        deleted = post_process.apply_deletion_post_processing(
            code_str, fsn=fsn, loinc_enhancements=LOINC_ENHANCEMENTS
        )
        assert deleted == code_str

    def test_deletions_in_long_code_string(self):
        code_str = "Myelin associated glycoprotein/Sulfated glucuronic paragloboside IgM Ab [Titer] in Serum by Immunoassay"
        fsn = "Myelin associated glycoprotein:Titr:Pt:Ser:SemiQn:IA"
        deleted = post_process.apply_deletion_post_processing(
            code_str, fsn=fsn, loinc_enhancements=LOINC_ENHANCEMENTS
        )
        assert (
            deleted == "Myelin associated glycoprotein/Sulfated glucuronic IgM Ab [Titer] Serum by"
        )

    def test_no_component_present(self):
        code_str = "MCH [Entitic mass] by Automated count"
        fsn = "Hemoglobin:EntMass:Pt:RBC:Qn:Automated count"
        deleted = post_process.apply_deletion_post_processing(
            code_str, fsn=fsn, loinc_enhancements=LOINC_ENHANCEMENTS
        )
        assert deleted == "MCH [Entitic by Automated"


class TestApplyDelimiterPostProcessing:
    def test_single_delimiter_swap(self):
        swapped = post_process.apply_delimiter_post_processing(
            "Neutrophils+Leukocytes in Blood by Automated count"
        )
        assert swapped == "Neutrophils/Leukocytes in Blood by Automated count"

    def test_multi_delimiter_swap(self):
        input = "Neutrophils+Leukocytes+Lymphocytes in Blood by Automated count"
        swapped = post_process.apply_delimiter_post_processing(input)
        assert swapped == "Neutrophils/Leukocytes/Lymphocytes in Blood by Automated count"

    def test_multi_swap_with_slash_already_present(self):
        # Ensures that the slash character is not swapped automatically
        input = "Neutrophils+Leukocytes/Lymphocytes in Serum&Plasma"
        swapped = post_process.apply_delimiter_post_processing(input)
        assert swapped == "Neutrophils/Leukocytes/Lymphocytes in Serum/Plasma"


class TestApplyDotNotationPostProcessing:
    def test_no_dots(self):
        assert post_process.apply_dot_flip_post_processing("Auto RBC (Bld)") == ""

    def test_non_dot_group_format(self):
        # Makes sure we don't catch stray periods that don't actually represent
        # chunked dot groups
        input = "Neutrophils+Leukocytes in Blood by Std. automated count"
        assert post_process.apply_dot_flip_post_processing(input) == ""

    def test_dot_group_expansion(self):
        input = "Albumin/Protein.total in Body fluid by Electrophoresis"
        expansion = post_process.apply_dot_flip_post_processing(input)
        assert expansion == "Albumin/total Protein in Body fluid by Electrophoresis"


class TestApplyPOCPostProcessing:
    def test_poc(self):
        assert (
            post_process.apply_point_of_care_post_processing("Auto RBC (Bld)")
            == "POC Auto RBC (Bld)"
        )


class TestModalityDropPostProcessing:
    def test_no_modality(self):
        input = "Protein Auto test strip dipstick [Mass/Vol]"
        dropped = post_process.apply_modality_drop_post_processing(
            input, system_axis="Urine", loinc_enhancements=LOINC_ENHANCEMENTS
        )
        assert dropped == input

    def test_just_modality(self):
        input = "fentaNYL [Presence] Urine by Screen method"
        dropped = post_process.apply_modality_drop_post_processing(
            input, system_axis="Urine", loinc_enhancements=LOINC_ENHANCEMENTS
        )
        assert dropped == "fentaNYL [Presence] by Screen method"

    def test_modality_with_parentheses(self):
        input = "RBC Auto (Bld) [#/Vol]"
        dropped = post_process.apply_modality_drop_post_processing(
            input, system_axis="Bld", loinc_enhancements=LOINC_ENHANCEMENTS
        )
        assert dropped == "RBC Auto [#/Vol]"

    def test_multiword_modality_with_preposition(self):
        input = "Creatinine [Mass/volume] in Serum or Plasma"
        dropped = post_process.apply_modality_drop_post_processing(
            input, system_axis="Ser/Plas", loinc_enhancements=LOINC_ENHANCEMENTS
        )
        assert dropped == "Creatinine [Mass/volume]"


class TestPoundSignPosttProcessing:
    def test_no_pound_signs(self):
        input = "Creatinine [Mass/volume] in Serum or Plasma"
        assert (
            post_process.apply_pound_sign_post_processing(input, outer_handling_method="drop")
            == input
        )

    def test_drop_outer(self):
        input = "Erythrocytes [#/volume] in Blood by Automated #"
        dropped = post_process.apply_pound_sign_post_processing(input, outer_handling_method="drop")
        assert dropped == "Erythrocytes [Number/volume] in Blood by Automated"

    def test_count_outer(self):
        input = "Erythrocytes [#/volume] in Blood by Automated #"
        dropped = post_process.apply_pound_sign_post_processing(
            input, outer_handling_method="count"
        )
        assert dropped == "Erythrocytes [Number/volume] in Blood by Automated Count"

    def test_multiple_inner_pounds(self):
        input = "Automated (# concentration) platelets [#/volume] in Blood"
        dropped = post_process.apply_pound_sign_post_processing(input, outer_handling_method="drop")
        assert dropped == "Automated (Number concentration) platelets [Number/volume] in Blood"


class TestSyntaxPostProcessing:
    def test_no_commas_or_prepositions(self):
        input = "Creatinine Serum or Plasma"
        assert post_process.apply_syntax_post_processing(input) == input

    def test_commas_and_prepositions(self):
        input = "Automated screen, Barbiturates, measured in solution"
        processed = post_process.apply_syntax_post_processing(input)
        assert processed == "Automated screen Barbiturates measured solution"

    def test_non_lab_preposition(self):
        input = "Albumin CSF Measurement by rapid-dye during electrophoresis"
        processed = post_process.apply_syntax_post_processing(input)
        assert processed == "Albumin CSF Measurement rapid-dye during electrophoresis"


class TestTruncationPostProcessing:
    def test_string_under_trunc_limit(self):
        input = "Barbiturates Screen Ql (U)"
        assert post_process.apply_truncation_post_processing(input) == input

    def test_string_over_trunc_limit(self):
        input = "Myelin associated glycoprotein/Sulfated glucuronic paragloboside IgM Ab [Titer] in Serum by Immunoassay"
        truncated = post_process.apply_truncation_post_processing(input)
        assert (
            truncated
            == "Myelin associated glycoprotein/Sulfated glucuronic paragloboside IgM Ab [Titer] in Se"
        )


class TestDetermineEligiblePostProcessingOptions:
    all_options: ClassVar[list[str]] = [
        "poc",
        "modality",
        "delimiter",
        "truncation",
        "syntax",
        "pound",
        "deletion",
        "dot",
    ]

    def test_ordinary_lcn(self):
        input = "Barbiturates [Presence] in Urine by Screen method"
        options = post_process._determine_eligible_post_processing(
            input, "Urine", LOINC_ENHANCEMENTS, self.all_options
        )
        assert options == ["poc", "modality", "syntax", "deletion"]

    def test_code_with_pounds_and_delimiters(self):
        input = "Neutrophils+Leukocytes [Entitic #/volume] in Blood by Automated count"
        options = post_process._determine_eligible_post_processing(
            input, "Bld", LOINC_ENHANCEMENTS, self.all_options
        )
        assert options == ["poc", "modality", "delimiter", "syntax", "pound", "deletion"]

    def test_code_with_dots_and_truncation(self):
        input = "Myelin associated glycoprotein/Sulfated glucuronic paragloboside protein.total IgM Ab [Titer] in Serum by Immunoassay"
        options = post_process._determine_eligible_post_processing(
            input, "Ser", LOINC_ENHANCEMENTS, self.all_options
        )
        assert options == ["poc", "modality", "truncation", "syntax", "deletion", "dot"]
