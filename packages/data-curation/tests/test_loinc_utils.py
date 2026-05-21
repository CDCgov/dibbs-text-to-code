import os
import random
import sys

import pytest

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from data_curation import loinc_utils

from utils import normalize
from utils import path
from utils import regex_patterns

enhancements = path.load_loinc_enhancements(os.getcwd())
LOINC_ENHANCEMENTS = normalize.merge_enhancements(enhancements)
assert len(LOINC_ENHANCEMENTS) > 0

random.seed(3141)


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
            "E SARS-CoV-2 gene Resp Ql NAA+probe",
        ),
        # More deletions than words
        ("B pert Spt Ql Cult", 10, "Spt pert B Ql Cult"),
    ],
)
class TestScrambleWordOrder:
    def test_scramble_word_order(self, text, max_perms, expected):
        """Test scramble word order."""
        result = loinc_utils.scramble_word_order(text, max_perms=max_perms)
        assert result == expected


class TestAxisIsValid:
    def test_null_string(self):
        is_valid = loinc_utils._axis_is_valid(None)
        assert not is_valid

    def test_empty_string(self):
        is_valid = loinc_utils._axis_is_valid("")
        assert not is_valid

    def test_dash(self):
        is_valid = loinc_utils._axis_is_valid("-")
        assert not is_valid

    def test_ordinary_word(self):
        is_valid = loinc_utils._axis_is_valid("Erythrocytes")
        assert is_valid

    def test_hyphenated_word(self):
        is_valid = loinc_utils._axis_is_valid("Creatinine-SerPlas")
        assert is_valid


class TestChooseFromLoincAxis:
    def test_null_string(self):
        choice = loinc_utils._choose_from_loinc_axis(None, LOINC_ENHANCEMENTS)
        assert choice == ""

    def test_empty_string(self):
        choice = loinc_utils._choose_from_loinc_axis("", LOINC_ENHANCEMENTS)
        assert choice == ""

    def test_non_mapped_grouping_string(self):
        choice = loinc_utils._choose_from_loinc_axis("{nursing_group}", LOINC_ENHANCEMENTS)
        assert choice == ""

    def test_component_string(self):
        choice = loinc_utils._choose_from_loinc_axis("Creatinine", LOINC_ENHANCEMENTS)
        assert choice == "Crea"

    def test_method_string(self):
        choice = loinc_utils._choose_from_loinc_axis("pediatric dermatology", LOINC_ENHANCEMENTS)
        assert choice == "Peds dermatology"


class TestCleanUnpairedParentheses:
    def test_no_unpaired(self):
        input = "Erythrocytes (RBC) Count"
        result = loinc_utils._clean_unpaired_parens(input)
        assert result == input

    def test_brackets_and_parens(self):
        input = "Erythrocytes (RBC) Count [#/volume]"
        result = loinc_utils._clean_unpaired_parens(input)
        assert result == input

    def test_no_parens_case(self):
        input = "Creatinine in Serum or Plasma"
        result = loinc_utils._clean_unpaired_parens(input)
        assert result == input

    def test_nested_case(self):
        input = "Erythrocytes [#(/volume] in ))))))) Blood (by] (Automated) count"
        result = loinc_utils._clean_unpaired_parens(input)
        assert result == "Erythrocytes [#/volume] in Blood by (Automated) count"


class TestExpandMeasurementProperty:
    def test_no_expansion(self):
        expansion = loinc_utils._expand_measurement_property("ACnc")
        assert expansion == "ACnc"
        expansion = loinc_utils._expand_measurement_property("Mass")
        assert expansion == "Mass"
        expansion = loinc_utils._expand_measurement_property("Ratio")
        assert expansion == "Ratio"

    def test_expansion(self):
        expansion = loinc_utils._expand_measurement_property("{Measurement}")
        assert expansion == "Ratio"
        expansion = loinc_utils._expand_measurement_property("{Measurement}")
        assert expansion == "Prctl"
        expansion = loinc_utils._expand_measurement_property("{Measurement}")
        assert expansion == "MCnt"


class TestFindSystemModality:
    def test_invalid_system_axes(self):
        modality = loinc_utils._find_system_modality("", None, LOINC_ENHANCEMENTS)
        assert modality is None
        modality = loinc_utils._find_system_modality("", "", LOINC_ENHANCEMENTS)
        assert modality is None

    def test_find_whole_word_modality(self):
        # Case where the modality has an abbreviation which is fully contained
        # within itself, e.g. "Urine" is often abbreviated "Ur"
        code_string = "fentaNYL [Presence] in Urine by Screen method"
        modality = loinc_utils._find_system_modality(code_string, "Urine", LOINC_ENHANCEMENTS)
        assert modality == ("Urine", 23, 28)

    def test_find_modality_with_preposition(self):
        code_string = "fentaNYL [Presence] in Urine by Screen method"
        modality = loinc_utils._find_system_modality(
            code_string, "Urine", LOINC_ENHANCEMENTS, include_preposition=True
        )
        assert modality == ("in Urine", 20, 28)

    def test_find_modality_when_abbreviated(self):
        # Tests the case where a modality is abbreviated, and there are other
        # bracketed units around to trip the function up
        code_string = "RBC Auto (Bld) [#/Vol]"
        modality = loinc_utils._find_system_modality(
            code_string, "Bld", LOINC_ENHANCEMENTS, include_parens=True
        )
        assert modality == ("(Bld)", 9, 14)

    def test_multi_word_modality(self):
        code_string = "Oxygen saturation in Arterial blood"
        modality = loinc_utils._find_system_modality(code_string, "BldA", LOINC_ENHANCEMENTS)
        assert modality == ("Arterial blood", 21, 35)


class TestGetComponentAxisFromFSN:
    def test_no_fsn(self):
        assert loinc_utils._get_component_axis_from_fsn(None) == ""

    def test_too_few_components(self):
        input = "axis1:axis2:axis3"
        component = loinc_utils._get_component_axis_from_fsn(input)
        assert component == ""

    def test_base_case_one_word_per_axis(self):
        input = "Erythrocytes:NCnc:Pt:Bld:Qn:Automated count"
        component = loinc_utils._get_component_axis_from_fsn(input)
        assert component == "Erythrocytes"

    def test_survey_question(self):
        input = "Thinking about how you live: I have enough money to cope:Find:Pt:^Patient:Ord:"
        component = loinc_utils._get_component_axis_from_fsn(input)
        assert component == "Thinking about how you live: I have enough money to cope"

    def test_solution_ratio(self):
        input = "Coagulation surface induced:Time:Pt:Bld^Control:Qn:Coag.saline 1:1"
        component = loinc_utils._get_component_axis_from_fsn(input)
        assert component == "Coagulation surface induced"

    def test_chemical_reaction(self):
        input = "Lactate dehydrogenase:CCnc:Pt:Body fld:Qn:Reaction: lactate to pyruvate"
        component = loinc_utils._get_component_axis_from_fsn(input)
        assert component == "Lactate dehydrogenase"


class TestGetPrecedingWord:
    def test_substring_not_in_string(self):
        assert loinc_utils._get_preceding_word("not present", "this is a string") == ""

    def test_substring_is_start_of_string(self):
        assert loinc_utils._get_preceding_word("First", "First is the worst") == ""

    def test_regular_case(self):
        loinc_code_string = "Creatinine [mass/volume] in Serum or Plasma"
        preceding_word = loinc_utils._get_preceding_word("Plasma", loinc_code_string)
        assert preceding_word == "or"


class TestParentheticalIsTrailingAcronym:
    def test_regular_is_acronym_case(self):
        code_string = "Red Blood Cell (RBC) Auto (Bld) [#/Vol]"
        acronym_parenthetical = regex_patterns.PARENTHESES_TEXT.search(code_string)
        acronym_expansion = loinc_utils._parenthetical_is_trailing_acronym(
            acronym_parenthetical, code_string
        )
        assert acronym_expansion == "Red Blood Cell"

    def test_regular_is_not_acronym_case(self):
        code_string = "Functional oxygen saturation in Arterial blood (SaO2)"
        acronym_parenthetical = regex_patterns.PARENTHESES_TEXT.search(code_string)
        acronym_expansion = loinc_utils._parenthetical_is_trailing_acronym(
            acronym_parenthetical, code_string
        )
        assert acronym_expansion is None

    def test_parenthetical_early_in_string(self):
        # Tests the try/except block in the code, which catches any parenthetical
        # that occurs too early in the string to be an acronym, and for which
        # confirming that will run off the front index of the string
        code_string = "Mean Corpuscular (MCHC) mass measurement"
        acronym_parenthetical = regex_patterns.PARENTHESES_TEXT.search(code_string)
        acronym_expansion = loinc_utils._parenthetical_is_trailing_acronym(
            acronym_parenthetical, code_string
        )
        assert acronym_expansion is None


class TestSusbtringIsEnclosedByParentheses:
    def test_no_parentheses(self):
        assert not loinc_utils._substring_is_contained_in_parens("There are no parens in me", 6, 9)

    def test_parentheses_at_beginning(self):
        assert loinc_utils._substring_is_contained_in_parens("(RBC) Erythrocytes Count", 1, 4)

    def test_parentheses_at_end(self):
        assert loinc_utils._substring_is_contained_in_parens("Arterial Blood (SaO2)", 16, 20)

    def test_ordinary_parentheses(self):
        assert loinc_utils._substring_is_contained_in_parens(
            "Hepatitis B Virus (HBV) Specimen", 19, 22
        )
