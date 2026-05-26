import os
import random
import sys

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from data_curation import data_emulation
from data_curation.schemas.loinc_struct import LabType, LoincStruct
from utils import normalize, path

enhancements = path.load_loinc_enhancements(os.getcwd())
LOINC_ENHANCEMENTS = normalize.merge_enhancements(enhancements)
assert len(LOINC_ENHANCEMENTS) > 0

FENTANYL_STRUCT = LoincStruct(
    long_common_name="fentaNYL [Presence] in Urine by Screen method",
    short_name="fentaNYL Ur Ql Scn",
    display_name="fentaNYL Screen Ql (U)",
    consumer_name="fentaNYL, Urine",
    fully_specified_name="fentaNYL:PrThr:Pt:Urine:Ord:Screen",
    lab_type=LabType.BOTH,
    class_type="DRUG/TOX",
    property="PrThr",
    time="Pt",
    system="Urine",
    scale="Ord",
    method="Screen",
)

ERYTHROCYTES_STRUCT = LoincStruct(
    long_common_name="Erythrocytes [#/volume] in Blood by Automated count",
    short_name="RBC # Bld Auto",
    display_name="RBC Auto (Bld) [#/Vol]",
    consumer_name="Red Blood Cell (RBC) Count, Blood",
    fully_specified_name="Erythrocytes:NCnc:Pt:Bld:Qn:Automated count",
    lab_type=LabType.BOTH,
    class_type="HEM/BC",
    property="NCnc",
    time="Pt",
    system="Bld",
    scale="Qn",
    method="Automated count",
)

CBC_STRUCT = LoincStruct(
    long_common_name="CBC W Auto Differential panel - Blood",
    short_name="CBC W Auto Diff Bld",
    display_name="CBC W Auto Differential panel (Bld)",
    consumer_name="CBC W Auto Differential Panel, Blood",
    fully_specified_name="Complete blood count W Auto Differential panel:-:Pt:Bld:Qn:",
    lab_type=LabType.ORDER,
    class_type="PANEL.HEM/BC",
    property=None,
    time="Pt",
    system="Bld",
    scale="Qn",
    method=None,
)


class TestBuildAndProcessTTCandHeuristics:
    # This function is really just re-using other functions, so we don't
    # need to test it too extensively
    def test_build_and_process(self):
        input = FENTANYL_STRUCT.long_common_name
        examples = data_emulation.build_and_process_ttc_and_heuristics(
            input,
            FENTANYL_STRUCT.fully_specified_name,
            FENTANYL_STRUCT.property,
            FENTANYL_STRUCT.system,
            [],
        )
        assert examples == [
            "Fenpat [Presence] in Scn Urine by Method of",
            "Fenpat Scn Urine Method",
            "fentaNYL Detection (Presence) in Urine by Screen method",
            "POC fentaNYL (Presence) by Screen method",
        ]


class TestBuildLOINCAxisExample:
    def test_regular_full_build(self):
        ex = data_emulation.build_loinc_axis_example(FENTANYL_STRUCT)
        assert ex == "Fenpat Position Emmision Tomography Ur Qual Scn"

    def test_skip_time(self):
        ex = data_emulation.build_loinc_axis_example(ERYTHROCYTES_STRUCT)
        assert ex == "Red cells Count Positron Emission Tomography Blood Quantitative Auto"

    def test_skip_scale(self):
        ex = data_emulation.build_loinc_axis_example(CBC_STRUCT)
        assert ex == "CBC W Auto Diff Position Emmision Tomography Whole blood Quan"


class TestBuildShortNameHyphenVariant:
    def test_no_hyphen(self):
        assert data_emulation.build_short_name_hyphen_variant(ERYTHROCYTES_STRUCT.short_name) == ""

    def test_with_hyphen(self):
        input = "Creat SerPl-mCnc"
        assert data_emulation.build_short_name_hyphen_variant(input) == "Creat SerPl"


class TestBuildTTCEnhancedExample:
    # The enhancement functions are already well-tesetd as part of the
    # augmentation package, so we don't need to do a ton of case-based
    # testing here
    def test_short_case(self):
        input = FENTANYL_STRUCT.long_common_name
        enhanced_ex = data_emulation.build_ttc_enhanced_example(input)
        assert enhanced_ex == "Fenpat [Presence] in Scn Urine by Method of"

    def test_longer_case(self):
        input = "Myelin associated glycoprotein/Sulfated glucuronic paragloboside IgM Ab [Measurement] in Serum"
        enhanced_ex = data_emulation.build_ttc_enhanced_example(input)
        assert (
            enhanced_ex
            == "glycoprotein/Sulfated glucuronic paragloboside Immunoglobulin M associated Myelin Ab [Measurement] in Serum"
        )


class TestBuildVendorFormulaExample:
    def test_standard_format_loinc_code(self):
        formula_result = data_emulation.build_vendor_formula_style_example(
            FENTANYL_STRUCT.long_common_name, FENTANYL_STRUCT.property, FENTANYL_STRUCT.system
        )
        assert formula_result == "Screening Urine fentaNYL Detection"

    def test_loinc_with_different_properties(self):
        formula_result = data_emulation.build_vendor_formula_style_example(
            ERYTHROCYTES_STRUCT.long_common_name,
            ERYTHROCYTES_STRUCT.property,
            ERYTHROCYTES_STRUCT.system,
        )
        assert formula_result == "Automated Blood Erythrocytes Count  (#/volume)"

    def test_nonstandard_lab_panel(self):
        formula_result = data_emulation.build_vendor_formula_style_example(
            CBC_STRUCT.long_common_name, CBC_STRUCT.property, CBC_STRUCT.system
        )
        assert formula_result == "Blood CBC W Auto Differential panel -"


class TestCreateSyntheticExamplesForCode:
    def test_standard_format_loinc_code(self):
        # Just a regular representative example of most types of LOINC codes
        synthetic_examples = data_emulation.create_synthetic_examples_for_code(FENTANYL_STRUCT)
        assert set(synthetic_examples["long_common_name"]) == {
            "fentaNYL Detection (Presence) Screen",
            "[Presence] Actiq Scn Method",
            "Sublimaze Radnuc.PET Ur Ql Scn",
            "of in [Presence] Urine by Actiq Scn Method",
            "POC Screening fentaNYL Detection",
            "fentaNYL (Presence) in Urine by Screen method",
            "Screening Urine fentaNYL Detection",
        }
        assert set(synthetic_examples["short_name"]) == {"POC fentaNYL Ql Scn"}
        assert set(synthetic_examples["display_name"]) == {
            "fentaNYL Qualitative",
            "Actiq Scn Ql (U)",
            "POC Sublimaze Scn (U)",
            "Sublimaze Scn (U) Ql",
            "fentaNYL Screen Qualitative Urine",
        }
        assert set(synthetic_examples["consumer_name"]) == {
            "POC UA fentaNYL",
            "POC fentaNYL,",
            "UA fentaNYL,",
            "Urine fentaNYL,",
            "Urn fentaNYL,",
            "fentaNYL, UA",
        }

    def test_loinc_with_acronym_and_type_variance(self):
        # A LOINC code with some different property expressions, leading
        # to different variations and post processing applied
        synthetic_examples = data_emulation.create_synthetic_examples_for_code(ERYTHROCYTES_STRUCT)
        assert set(synthetic_examples["long_common_name"]) == {
            "Automated Blood Erythrocytes Count (#/volume)",
            "Erythrocytes Count [#/volume] in Whole Blood by Automated count",
            "POC Automated Erythrocytes Count (#/volume)",
            "POC Erythrocytes in Blood Automated count",
            "Red blood cells absolutes Random Whole blood Quantitative Auto",
            "by corpuscle [#/volume] in Blood blood Red Auto count",
            "corpuscle [Number/volume] Blood blood Red Auto count",
        }
        assert set(synthetic_examples["short_name"]) == {"RBC Count Auto"}
        assert set(synthetic_examples["display_name"]) == {
            "(Bld) Auto [#/Vol] Erythrocytes",
            "Auto [Number/Vol] Erythrocytes",
            "Erythrocytes Auto [#/Vol] (Bld)",
            "Erythrocytes [#/Vol]",
            "POC RBC Auto Absolute [Number/Vol]",
            "POC RBC Auto [Number/Vol]",
            "RBC Auto (Bld) #/Vol",
            "RBC Auto Absolute [#/Vol]",
        }
        assert set(synthetic_examples["consumer_name"]) == {
            "(RBC) Cell Blood Count, Blood Red",
            "POC Cell Blood Count, Blood",
            "POC RBC Count WB",
            "Red (RBC) Blood Blood Cell Count,",
            "Red (RBC) Blood Cell Count",
            "Red Plasma Cell Count, Blood",
            "Red Serum, Plasma or Blood Cell Count, Blood",
            "Red WB Cell Blood",
        }

    def test_nonstandard_lab_panel_loinc(self):
        # A LOINC code representing the family of "lab panel" LOINCs, which
        # include batteries of other tests rather than look for individual
        # measurements or organisms
        synthetic_examples = data_emulation.create_synthetic_examples_for_code(CBC_STRUCT)
        assert set(synthetic_examples["long_common_name"]) == {
            "Blood CBC W Auto Differential panel -",
            "CBC W Auto Diff Blood - Pnl",
            "CBC W Auto Diff Radnuc.PET Whole blood Quantitative",
            "CBC W Auto Differential panel - Serum, Plasma or Blood",
            "POC Blood CBC W Auto Differential panel",
            "POC CBC W Auto Diff Blood Pnl",
            "POC CBC W Auto Differential panel -",
        }
        assert set(synthetic_examples["short_name"]) == {"POC CBC W Auto Diff"}
        assert set(synthetic_examples["display_name"]) == {
            "CBC Auto W Pnl Diff (Bld)",
            "CBC W Auto Differential panel",
            "POC CBC W Auto Differential",
            "W Diff Auto",
            "W Diff Auto Pnl CBC (Bld)",
            "W Pnl Diff",
        }
        assert set(synthetic_examples["consumer_name"]) == {
            "CBC W Auto Differential Panel, Plasma",
            "CBC W Auto Differential Panel, WB",
            "POC CBC W Auto Differential Panel Plasma",
            "POC CBC W Auto Differential Panel Serum Plasma or Blood",
            "POC W Auto Panel, CBC",
            "W Auto CBC Differential Blood Panel,",
            "W Auto Differential Blood",
            "W Auto Differential Panel, Blood CBC",
        }


class TestGetBracketVariations:
    def test_no_brackets(self):
        input = CBC_STRUCT.long_common_name
        assert data_emulation.get_bracket_variations(input) == []

    def test_brackets_present(self):
        input = ERYTHROCYTES_STRUCT.long_common_name
        variations = data_emulation.get_bracket_variations(input)
        # Multiple spaces are handled by the orchestrator function so this isn't
        # passed on to future handlers
        assert variations == [
            "Erythrocytes  in Blood by Automated count",
            "Erythrocytes (#/volume) in Blood by Automated count",
            "Erythrocytes #/volume in Blood by Automated count",
        ]


class TestGetMeasurementVariations:
    def test_no_measurement_word(self):
        input = "Oxygen saturation in Arterial blood"
        assert data_emulation.get_measurement_variation(input, "-") == []

    def test_variant_with_no_mapping(self):
        input = "Protein [Mass/volume] in Urine by Automated test strip"
        variation = data_emulation.get_measurement_variation(input, "MCnc")
        assert variation == ["Protein [Mass/volume] in Urine Level by Automated test strip"]

    def test_general_bracket_case(self):
        input = FENTANYL_STRUCT.long_common_name
        variation = data_emulation.get_measurement_variation(input, FENTANYL_STRUCT.property)
        assert variation == ["fentaNYL Detection [Presence] in Urine by Screen method"]

    def test_fallback_case(self):
        input = "Oxygen saturation in Arterial blood"
        assert data_emulation.get_measurement_variation(input, "MFr") == [
            "Oxygen saturation in Arterial blood Measurement"
        ]


class TestGetModalityVariations:
    def test_no_modality(self):
        input = "Protein Auto test strip [Mass/Vol]"
        variations = data_emulation.get_modality_variations(input, "Urine")
        assert variations == []

    def test_big_three_modality_with_swap(self):
        input = "Creatinine [Mass/volume] in Serum or Plasma"
        variations = data_emulation.get_modality_variations(input, "Ser/Plas")
        assert variations == [
            "Serum or Plasma Creatinine [Mass/volume]",
            "Creatinine [Mass/volume] in SerP",
            "Creatinine [Mass/volume] in Blood",
        ]

    def test_poc_modality(self):
        input = ERYTHROCYTES_STRUCT.long_common_name
        variations = data_emulation.get_modality_variations(input, "Bld")
        assert variations == [
            "Blood Erythrocytes [#/volume] by Automated count",
            "Erythrocytes [#/volume] in Whole blood by Automated count",
            "Erythrocytes [#/volume] in Serum, Plasma or Blood by Automated count",
            "Erythrocytes [#/volume] in Whole Blood by Automated count",
        ]


class TestParenthesesVariations:
    def test_no_parens_group(self):
        assert data_emulation.get_parens_variations(CBC_STRUCT.long_common_name) == []

    def test_deletion_with_no_acronym(self):
        variants = data_emulation.get_parens_variations(CBC_STRUCT.display_name)
        assert variants == ["CBC W Auto Differential panel"]

    def test_trailing_acronym_replacement(self):
        variants = data_emulation.get_parens_variations(ERYTHROCYTES_STRUCT.consumer_name)
        # As usual, multi-space truncation is handled by other orchestrator functions
        assert variants == ["Red Blood Cell  Count, Blood", "RBC Count, Blood"]


class TestQGroupVariations:
    def test_no_q_group(self):
        assert data_emulation.get_q_variations(ERYTHROCYTES_STRUCT.long_common_name) == []

    def test_qualitative_single_modality(self):
        variations = data_emulation.get_q_variations(FENTANYL_STRUCT.display_name)
        assert variations == ["fentaNYL Screen Urine", "fentaNYL Screen Qualitative Urine"]

    def test_quantitative_multi_modality(self):
        variations = data_emulation.get_q_variations(
            "Barbiturates [Mass/Volume] Qn (Ser/Plas) by Screen Method"
        )
        assert variations == [
            "Barbiturates [Mass/Volume] Plasma by Screen Method",
            "Barbiturates [Mass/Volume] Quantitative Plasma by Screen Method",
        ]


class TestAllocateGeneratedLOINCs:
    def test_allocate_no_generated_codes(self):
        assert data_emulation._allocate_generated_loincs_to_training_arrays(
            FENTANYL_STRUCT.long_common_name, [], [], [], []
        ) == ([], [], [])

    def test_single_generated_code(self):
        assert data_emulation._allocate_generated_loincs_to_training_arrays(
            FENTANYL_STRUCT.long_common_name, [FENTANYL_STRUCT.display_name], [], [], []
        ) == ([], [], [(FENTANYL_STRUCT.long_common_name, FENTANYL_STRUCT.display_name)])

    def test_ordinary_allocation(self):
        generated_loincs = [
            FENTANYL_STRUCT.long_common_name,
            FENTANYL_STRUCT.display_name,
            FENTANYL_STRUCT.consumer_name,
        ]
        search_array, reranker_array, validation_array = (
            data_emulation._allocate_generated_loincs_to_training_arrays(
                FENTANYL_STRUCT.short_name, generated_loincs, [], [], []
            )
        )
        assert search_array == [(FENTANYL_STRUCT.short_name, FENTANYL_STRUCT.consumer_name)]
        assert reranker_array == [(FENTANYL_STRUCT.short_name, FENTANYL_STRUCT.display_name)]
        assert validation_array == [(FENTANYL_STRUCT.short_name, FENTANYL_STRUCT.long_common_name)]


class TestChooseAndApplyVariationHeuristics:
    def test_no_variations(self):
        assert data_emulation._choose_and_apply_heuristics("Urine", "-", "-") == ""

    def test_ordinary_measure_modality_bracket_lcn(self):
        # Different seed gets different modality behavior
        random.seed(2)
        variation = data_emulation._choose_and_apply_heuristics(
            FENTANYL_STRUCT.long_common_name, FENTANYL_STRUCT.property, FENTANYL_STRUCT.system
        )
        assert variation == "fentaNYL Detection (Presence) in Urine by Screen method"

    def test_q_group_parens_dn(self):
        variation = data_emulation._choose_and_apply_heuristics(
            FENTANYL_STRUCT.display_name, FENTANYL_STRUCT.property, FENTANYL_STRUCT.system
        )
        assert variation == "fentaNYL Screen Ql"


class TestChooseAndApplyPostProcessing:
    def test_ordinary_lcn(self):
        post_processed = data_emulation._choose_and_apply_post_processing(
            FENTANYL_STRUCT.long_common_name,
            FENTANYL_STRUCT.fully_specified_name,
            FENTANYL_STRUCT.system,
            LOINC_ENHANCEMENTS,
            data_emulation.BASE_POST_PROCESSING_OPTIONS,
        )
        assert post_processed == "POC fentaNYL [Presence] Urine Screen method"

    def test_code_with_pounds_and_delimiters(self):
        input = "Neutrophils+Leukocytes [Entitic #/volume] in Blood by Automated count"
        fsn = "Neutrophils+Leukocytes:MCnc:Pt:Bld:"
        post_processed = data_emulation._choose_and_apply_post_processing(
            input, fsn, "Bld", LOINC_ENHANCEMENTS, data_emulation.BASE_POST_PROCESSING_OPTIONS
        )
        assert post_processed == "Neutrophils/Leukocytes [Entitic #/volume] by Automated count"

    def test_code_with_dots_and_truncation(self):
        input = "Myelin associated glycoprotein/Sulfated glucuronic paragloboside protein.total IgM Ab [Titer] in Serum by Immunoassay"
        fsn = "Myelin associated glycoprotein:CCnc:Pt:Ser/Plas:Ord:"
        post_processed = data_emulation._choose_and_apply_post_processing(
            input, fsn, "Ser/Plas", LOINC_ENHANCEMENTS, data_emulation.BASE_POST_PROCESSING_OPTIONS
        )
        assert (
            post_processed
            == "Myelin associated glycoprotein/Sulfated glucuronic paragloboside protein.total IgM Ab"
        )


class TestCandidateIsValid:
    def test_null_code(self):
        assert not data_emulation._codestring_is_valid_candidate(
            None, FENTANYL_STRUCT.long_common_name
        )

    def test_empty_code(self):
        assert not data_emulation._codestring_is_valid_candidate(
            "", FENTANYL_STRUCT.long_common_name
        )

    def test_equivalent_code(self):
        assert not data_emulation._codestring_is_valid_candidate(
            FENTANYL_STRUCT.long_common_name, FENTANYL_STRUCT.long_common_name
        )

    def test_valid_code(self):
        assert data_emulation._codestring_is_valid_candidate(
            FENTANYL_STRUCT.display_name, FENTANYL_STRUCT.long_common_name
        )


class TestDetermineEligiblePatternHeuristics:
    def test_no_variations(self):
        assert data_emulation._determine_eligible_pattern_heuristics("Urine", "-", "-") == []

    def test_ordinary_measure_modality_bracket_lcn(self):
        heuristics = data_emulation._determine_eligible_pattern_heuristics(
            FENTANYL_STRUCT.long_common_name, FENTANYL_STRUCT.property, FENTANYL_STRUCT.system
        )
        assert heuristics == ["measurement", "modality", "brackets"]

    def test_q_group_parens_dn(self):
        heuristics = data_emulation._determine_eligible_pattern_heuristics(
            FENTANYL_STRUCT.display_name, FENTANYL_STRUCT.property, FENTANYL_STRUCT.system
        )
        assert heuristics == ["q group", "parens"]


class TestGetSingleWordMethod:
    def test_no_method(self):
        assert data_emulation._get_single_word_method(CBC_STRUCT.long_common_name) == ("", None)

    def test_screening(self):
        input = FENTANYL_STRUCT.long_common_name
        method_word = data_emulation._get_single_word_method(input)
        assert method_word == ("Screening", -3)

    def test_automated(self):
        input = ERYTHROCYTES_STRUCT.long_common_name
        method_word = data_emulation._get_single_word_method(input)
        assert method_word == ("Automated", -3)


class TestGetMeasurementUnitWord:
    def test_null_property_no_word(self):
        assert (
            data_emulation._get_measurement_unit_word(
                CBC_STRUCT.long_common_name, CBC_STRUCT.property
            )
            == ""
        )

    def test_calculation_determination(self):
        input = "Base excess in Arterial blood by calculation"
        result = data_emulation._get_measurement_unit_word(input, "SCnc")
        assert result == "Determination"

    def test_specimen_detected(self):
        input = "Acute leukemia markers [Interpretation] in Specimen"
        result = data_emulation._get_measurement_unit_word(input, "Nar")
        assert result == "Detected"

    def test_ratio(self):
        input = "Acylcarnitine/Carnitine.free (C0) [Ratio] in Urine"
        result = data_emulation._get_measurement_unit_word(input, "Rto")
        assert result == "Ratio"

    def test_percentage(self):
        input = "Alkaline phosphatase.bile/Alkaline phosphatase.total in Serum or Plasma"
        result = data_emulation._get_measurement_unit_word(input, "CFr")
        assert result == "Percentage"

    def test_presence_detection(self):
        assert (
            data_emulation._get_measurement_unit_word(
                FENTANYL_STRUCT.long_common_name, FENTANYL_STRUCT.property
            )
            == "Detection"
        )

    def test_count(self):
        result = data_emulation._get_measurement_unit_word(
            ERYTHROCYTES_STRUCT.long_common_name, ERYTHROCYTES_STRUCT.property
        )
        assert result == "Count"

    def test_moles_measurement(self):
        input = "Allocystathionine [Moles/volume] in Serum or Plasma"
        result = data_emulation._get_measurement_unit_word(input, "SCnc")
        assert result == "Measurement"

    def test_mass_level(self):
        input = "Creatinine [Mass/volume] in Serum or Plasma"
        result = data_emulation._get_measurement_unit_word(input, "MCnc")
        assert result == "Level"

    def test_mcnc_measurement(self):
        pass
        input = "Caffeine in Body fluid [Measurement]"
        result = data_emulation._get_measurement_unit_word(input, "SMCnc")
        assert result == "Measurement"

    def test_mfr(self):
        input = "Methemoglobin and sulfhemoglobin panel - Blood"
        result = data_emulation._get_measurement_unit_word(input, "MFr")
        assert result == "Measurement"
