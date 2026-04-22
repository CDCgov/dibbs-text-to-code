"""
data_curation.data_emulation
~~~~~~~~~~~~~~~~~~~~~~~~~

This module contains the primary code for generating synthetic data samples
designed to emulate production eCR data. The functions within employ a set
of rules designed to create data samples that mimic patterns derived from
analyzing large sets of real production data. Broadly, these patterns are
split into three distinct types:

1. Whole-Code Formulas: these patterns directly apply a "recipe" to a 
   particular LOINC code name variant. This recipe modifies, substitutes,
   and rearranges text within the existing string to make it conform 
   directly to structures observed to be common during production data
   analysis.
2. Axis-Based Build Patterns: these patterns construct a "name-like" 
   variant for a LOINC code by combining the specific axis properties of 
   the code (System, Method, Scale, etc.) with an "Enhancement Dictionary"
   lookup. Resulting strings are built by adding relevant text derived
   from the LOINC code's properties and Related Names to a logical 
   sequencing of code words.
3. Semantic Variation: these patterns alter or modify the existing code
   text of a LOINC string, rearranging it or otherwise augmenting it, 
   without directly building a new code from scratch. This results in a
   smaller scale of changes than the previous two patterns, but captures a
   wide range of nuance in how production data might actually be reported
   with minor deviations from the norm.

This data emulation code relies on a set of LOINC data files with information
pulled from the LOINC API, the RELMA database, and UMLS. For each row in the
files (i.e. each LOINC code), a full LOINC Structure Object is built (see
data_curation.schemas) to store its properties. Then, for each name variant
that exists for the code, the three pattern-types described above are applied 
in triage. First, any relevant "whole formula" examples are generated. Then,
the LOINC Struct's axis properties are used to generate "enhanced builds."
Finally, the existing name variant text is modified with semantic variation.
This collection of examples is stored in a pairwise dictionary that is 
written to one (or more) files for future training and testing purposes.
"""


import math
import os
import random
import sys
import typing

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from data_curation.loinc_enhancement import enhance_loinc_str
from data_curation.post_process import (
    apply_deletion_post_processing,
    apply_delimiter_post_processing,
    apply_dot_flip_post_processing,
    apply_modality_drop_post_processing,
    apply_point_of_care_post_processing,
    apply_pound_sign_post_processing,
    apply_syntax_post_processing,
    apply_truncation_post_processing,
    _determine_eligible_post_processing
)
from data_curation.schemas import loinc_struct as schemas
from data_curation.loinc_utils import (
    scramble_word_order,
    _axis_is_valid,
    _choose_from_loinc_axis,
    _clean_unpaired_parens,
    _expand_measurement_property,
    _find_system_modality,
    _get_component_axis_from_fsn,
    _parenthetical_is_trailing_acronym
)

from utils import normalize
from utils import path
from utils.regex_patterns import (
    BRACKETED_TEXT,
    PARENTHESES_TEXT,
    Q_GROUP,
    MULTIPLE_SPACE
)

enhancements = path.load_loinc_enhancements(os.getcwd())
LOINC_ENHANCEMENTS = normalize.merge_enhancements(enhancements)
assert len(LOINC_ENHANCEMENTS) > 0

# Parameters for snoinc reading and ultimate data generation
SNOINC_DATA_FILE = "../../../../data/snoinc_extracts/loinc_lab_names_20260223.csv"
SEARCH_TRAINING_OUT_FILE = "../../../../data/training_files/prod_emulated_positive_pairs_no_cn.txt"
RERANKER_TRAINING_OUT_FILE = "../../../../data/training_files/prod_emulated_reranker_pairs_no_cn.txt"
TESTING_OUT_FILE = "../../../../data/training_files/prod_emulated_validation_set_no_cn.txt"

# We have found Consumer Name to be actively detrimental for training and 
# testing. We recommend excluding it from the final output written to the
# training and validation files.
INCLUDE_CN_IN_FINAL_OUTPUT = False

# We exclude FSN from training here because the variants are all one-to-many
# mappings that will confound the algorithm; e.g., the word "creatinine" maps to
# 43 different LOINCs, which isn't helpful. We'll still be able to map to it, we
# just won't train on variants of it because there isn't enough information.
NAME_VARIANTS = [
    "long_common_name", "short_name", "display_name", "consumer_name"
]
LOINC_AXES = ["component", "property", "time", "system", "scale", "method"]
MAX_NUM_AXIS_REPLACEMENT_TRIES = 100
BIG_THREE_LIQUID_MODALITIES = ["Serum", "Plasma", "Blood", "Serum or Plasma", "Serum, Plasma or Blood"]
POC_SYSTEMS = ["Bld", "Ser/Plas/Bld"]
SINGLE_WORD_METHOD_MAPPINGS = {
    "by screen method": "Screening",
    "by automated count": "Automated"
}
BASE_POST_PROCESSING_OPTIONS = [
    "poc", "modality", "delimiter", "truncation", "syntax", "pound", "deletion", "dot"
]
BASE_HEURISTIC_OPTIONS = ["measurement", "q group", "modality", "parens", "brackets"]


def build_and_process_ttc_and_heuristics(
        code_str: str,
        fsn: str,
        property_axis: str,
        system_axis: str,
        variations: typing.List[str]
    ):
    """
    Given a LOINC code string and some of its property information, construct
    a TTC-style "enhanced" example of the code, then apply any eligible
    post-processing. This function is primarily an orchestrator of its 
    internal functions.

    :param code_str: The text string of a LOINC code name variant.
    :param fsn: The fully specified name of the LOINC code.
    :param property_axis: The property axis of the LOINC code proper.
    :param system_axis: The system axis of the LOINC code proper.
    :param variations: The iteratively built list of variations generated
      for this LOINC code, which the function will add to throughout.
    """
    ttc_build = build_ttc_enhanced_example(code_str)
    if _codestring_is_valid_candidate(ttc_build, code_str):
        variations.append(ttc_build)
        ttc_processed = _choose_and_apply_post_processing(
            ttc_build,
            fsn,
            system_axis,
            LOINC_ENHANCEMENTS,
            BASE_POST_PROCESSING_OPTIONS
        )
        if _codestring_is_valid_candidate(ttc_processed, code_str):
            variations.append(ttc_processed)
    
    rule_based_example = _choose_and_apply_heuristics(
        code_str, property_axis, system_axis
    )
    if _codestring_is_valid_candidate(rule_based_example, code_str):
        variations.append(rule_based_example)
    # Make a different set of random choices for variety
    heuristic_ex_to_process = _choose_and_apply_heuristics(
        code_str, property_axis, system_axis
    )
    heuristic_ex_to_process = _choose_and_apply_post_processing(
        heuristic_ex_to_process,
        fsn,
        system_axis,
        LOINC_ENHANCEMENTS,
        BASE_POST_PROCESSING_OPTIONS
    )
    if _codestring_is_valid_candidate(heuristic_ex_to_process, code_str):
        variations.append(heuristic_ex_to_process)
    
    return variations


def build_loinc_axis_example(
        loinc_code: schemas.LoincStruct,
        skip_time: bool = False,
        skip_scale: bool = False
    ) -> str:
    """
    Given a LOINC code structure, directly construct a "LOINC-like" variant
    for that code by repeatedly choosing a valid enhancement word for
    that axis directly from our dictionary of axis-synonyms and 
    abbreviations. This build pattern represents getting a sample of data in
    which everything is "close to" the correct code, but nothing is outright
    the same.

    :param loinc_code: A codified LOINC Struct object representing a LOINC
      code extracted from the API.
    :param skip_time: Optionally, whether to skip the "time" axis when 
      building up the variant. Production samples tend to be mixed on
      this axis, with some having it, others not.
    :param skip_scale: Optionally, whether to skip the "scale" axis when
      building up the variant. Production samples tend to be mixed on
      this axis, with some having it, others not.
    :returns: A synthetic variant built directly out of synonym-searching the
      LOINC code's various axes.
    """
    # Component wasn't pulled in the sheet so need to derive it from FSN
    component = _get_component_axis_from_fsn(
        getattr(loinc_code, "fully_specified_name")
    )
    if component == "":
        return ""
    
    core_concept = _choose_from_loinc_axis(component, LOINC_ENHANCEMENTS)

    # Rare exception case when the LOINC code has no "base" concept,
    # so there's nothing to build around here
    if core_concept == "":
        return ""    
    built_code = core_concept + " "

    # Since we call this function a bunch, want to use list compression here,
    # but DeMorgan's Law just means the parens here amount to "if skip, remove"
    relevant_axes = [
        c for c in LOINC_AXES if c != "component" and \
            (c != "time" or not skip_time) and \
                (c != "scale" or not skip_scale)
    ]

    for axis in relevant_axes:    
        choice_for_axis = _choose_from_loinc_axis(
            getattr(loinc_code, axis), LOINC_ENHANCEMENTS
        )
        if choice_for_axis != "":
            built_code += choice_for_axis + " "
    
    return built_code.strip()


def build_short_name_hyphen_variant(code_str: str) -> str:
    """
    Simple function that creates a variant of a short name obtained by
    taking all code text that precedes a measurement-delimiting hyphen.

    :param code_str: The text string of a LOINC code short name.
    :returns: The hyphen-truncated variation.
    """
    if "-" in code_str:
        return code_str.split("-")[0]
    return ""


def build_ttc_enhanced_example(code_str: str) -> str:
    """
    Given a LOINC code string, generate a "TTC Enhanced" version of the
    string. A TTC Enhanced code string contains one or more enhancements
    made to the string (enhancements are abbreviation and acronym 
    substitutions based on the merged RELMA and UMLS database), followed
    by one or more word swaps.

    :param code_str: A text string of a LOINC code name variant.
    :returns: A version of the string with enhancements performed.
    """
    num_enhancements_to_attempt = 1 + math.ceil(
        float(len(code_str.split())) / 4.0
    )
    ex_code = enhance_loinc_str(
        code_str, 'all', num_enhancements_to_attempt, num_enhancements_to_attempt
    )
    ex_code = scramble_word_order(ex_code, 3)
    return ex_code


def build_vendor_formula_style_example(
        code_str: str, property_axis: str, system_axis: str
    ) -> str:
    """
    Given a LOINC code string and a few of its properties, create a synthetic
    variant of that code string that conforms to a few common trends observed
    in production data. There is a particular format of some vendor-supplied
    data that looks like

      method_word modality core_component (acronym) measurement_word (unit text)
    
    This format is common enough that for any LOINC code that can have an 
    example in this format be constructed, it's a good idea to do so.

    :param code_str: The text string of a LOINC name variant, typically the
      long common name.
    :param property_axis: The property axis of the LOINC code proper.
    :param system_axis: The system axis of the LOINC code proper.
    :returns: A synthetic variant of the code that looks like the formula above.
    """
    # Step 1: Identify the detection method, if any, before we mess with words
    detection_tuple = _get_single_word_method(code_str)
    detection_method_compressed = detection_tuple[0]
    if detection_tuple[1] is not None:
        # We found a method compression, but the old text is still there
        # Take it out
        code_str = " ".join(code_str.split()[:detection_tuple[1]])

    # Step 2: Insert an applicable measurement word without disrupting brackets
    # or modality
    measurement_variants = get_measurement_variation(code_str, property_axis)
    find_modality_in = code_str
    if len(measurement_variants) > 0:
        find_modality_in = measurement_variants[0]

    # Step 3: Move the modality to the front of the word
    modality_variants = get_modality_variations(find_modality_in, system_axis)
    if len(modality_variants) == 0:
        return ""
    
    # Step 4: Put the detection method, if it existed, at the very front
    # Because it's a list, we know first element is always the one with the
    # whole modality chunk moved to the front, preposition dropped
    result = detection_method_compressed + " " + modality_variants[0]
    result = result.strip()

    # Step 5: If there are unit brackets, move them to the end and 
    # turn them into parens
    bracketed_text = BRACKETED_TEXT.search(result)
    if bracketed_text is not None:
        # Presence is specifically excluded here and gets dropped
        if "presence" in bracketed_text.group(0).lower():
            result = result[:bracketed_text.span()[0]].strip()
        else:
            result = result[:bracketed_text.span()[0]].strip() + " " + \
                result[min(bracketed_text.span()[1], len(result)):].strip()
            result += " " + bracketed_text.group(0).replace('[', '(').replace(']', ')')
    
    return result


def create_synthetic_examples_for_code(
        loinc_code: schemas.LoincStruct
    ) -> dict[str, typing.List[str]]:
    """
    Given a LOINC code structured object, perform a comprehensive panel of
    synthetic data generation. For each name variant in the code structure
    that is present, apply eligible forms of variation or direct build
    patterns to create rich synthetic modifications of the original name
    variant. Then, for each variant generated, apply post-processing to 
    further reduce standardization to the norm. All resulting synthetic
    examples generated are stored in a dictionary structure mapping the
    base name variant of the LOINC code to a list of generated synthetic
    variants.

    :param loinc_code: A codified LOINC Struct object representing a LOINC
      code and its detailed information, extracted from the LOINC API.
    :returns: A dictionary mapping base name variants of the given LOINC 
      code to lists of synthetic examples built up out of that variant.
    """
    synthetic_examples = {}
    # Component wasn't separately pulled down as data, but we can determine it
    # by parsing the FSN
    fsn = loinc_code.fully_specified_name
    for nv in NAME_VARIANTS:
        variations = []

        # Short names are the easiest to handle because they have only a small
        # block of options; just do it first
        if nv == "short_name":
            sn = getattr(loinc_code, nv)
            # Short names' only direct build pattern is the hyphen
            hyphen_build = build_short_name_hyphen_variant(sn)
            if _codestring_is_valid_candidate(hyphen_build, sn):
                variations.append(hyphen_build)
            
            # We'll also try a post-process on the short name proper
            processed_sn = _choose_and_apply_post_processing(
                sn,
                fsn,
                getattr(loinc_code, "system"),
                LOINC_ENHANCEMENTS,
                ["dot", "poc", "pound", "modality"]
            )
            if _codestring_is_valid_candidate(processed_sn, sn):
                variations.append(processed_sn)

        else:
            name = getattr(loinc_code, nv)

            # Lots of data points to add here, it's the most common variant
            # that inputs seem to key off of. We'll handle its special builds
            # here, then other processing will get applied later.
            if nv == "long_common_name":
                # We'll start with an example constructed straight from axes
                axis_build = build_loinc_axis_example(
                    loinc_code,
                    skip_time=random.choice([True, False]),
                    skip_scale=random.choice([True, False])
                )
                if _codestring_is_valid_candidate(axis_build, name):
                    variations.append(axis_build)

                # Then we'll apply the vendor build pattern
                vendor_build = build_vendor_formula_style_example(
                    name,
                    getattr(loinc_code, "property"),
                    getattr(loinc_code, "system")
                )
                if _codestring_is_valid_candidate(vendor_build, name):
                    variations.append(vendor_build)
                    # We'll take a post-processed (further modified) version of
                    # that build, too
                    processed_vendor = _choose_and_apply_post_processing(
                        vendor_build,
                        fsn,
                        getattr(loinc_code, "system"),
                        LOINC_ENHANCEMENTS,
                        BASE_POST_PROCESSING_OPTIONS
                    )
                    if _codestring_is_valid_candidate(processed_vendor, name):
                        variations.append(processed_vendor)

            # Here we'll handle the special cases for display names and consumer names
            # They don't have build patterns directly, so they'll get one extra
            # example each of a TTC enhanced code and a heuristics code
            elif nv == "display_name" or nv == "consumer_name":
                variations = build_and_process_ttc_and_heuristics(
                    name,
                    fsn,
                    getattr(loinc_code, "property"),
                    getattr(loinc_code, "system"),
                    variations
                )
            
            # Finally, add a TTC enhanced version and a heuristics code for 
            # all non short names
            variations = build_and_process_ttc_and_heuristics(
                name,
                fsn,
                getattr(loinc_code, "property"),
                getattr(loinc_code, "system"),
                variations
            )

        synthetic_examples[nv] = variations
        
    # Before we return, we'll de-duplicate the examples, just in case
    # we somehow randomly generated two that are the same
    # We'll also throw away any examples that are one word
    for k in synthetic_examples:
        single_spaced_exs = [MULTIPLE_SPACE.sub(' ', se).strip() for se in synthetic_examples[k]]
        multi_word_exs = [ex for ex in single_spaced_exs if len(ex.split()) > 1]
        synthetic_examples[k] = list(set(multi_word_exs))
    return synthetic_examples


def get_bracket_variations(code_str: str) -> typing.List[str]:
    """
    Given a LOINC code string, generate semantic variations of that string 
    that modify how brackets within the string are used (or whether they
    remain in the string at all). Bracket variance is one of the most 
    frequent departures-from-standard we see in production-grace code
    strings. 

    :param code_str: The text string of a LOINC name variant.
    :returns: A list containing the synthetic versions of the LOINC code 
      string, with use of brackets modified.
    """
    variations = []
    bracketed_text = BRACKETED_TEXT.search(code_str)
    if bracketed_text is not None:
        # Version 1: Delete the whole bracketed chunk
        variations.append(BRACKETED_TEXT.sub('', code_str).strip())
        # Version 2: Replace brackets with parentheses
        variations.append(code_str.replace('[', '(').replace(']', ')').strip())
        # Version 3: Drop just the bracket characters
        variations.append(code_str.replace('[', '').replace(']', '').strip())
    return variations


def get_measurement_variation(
        code_str: str, property_axis: str
    ) -> typing.List[str]:
    """
    Given a LOINC code string and its associated property axis, create a 
    variant of the code string that includes a "measurement"-style word 
    inserted at the appropriate point. Measurement-style words include
    things like "Detection," "Level," "Ratio," "Determination," and the
    like. These words are often present in production data to denote a
    specific instantiation or performance of a test, but the position of
    these words is often a function of the rest of the code. This function
    applies several common rules to locate it appropriately. Note that
    while this function will only generate one variation of a code, the
    return type is still a list to correspond to the established
    convention that `get_XXX_variation` functions return an `Iterable`
    from which elements can be randomly chosen.

    :param code_str: The text string of a LOINC name variant.
    :param property_axis: The property axis of the LOINC code proper.
    :returns: A list containing a synthetically generated example with a
      word denoting measurement added to it.
    """
    variations = []
    measurement_word = _get_measurement_unit_word(code_str, property_axis)
    bracketed_text = BRACKETED_TEXT.search(code_str)

    if measurement_word != "":
        # If "by" occurs in the code string but we can't method-map it, it's
        # a special clause, so put the measurement before it
        if _get_single_word_method(code_str)[0] == "" and " by " in code_str:
            # As with method compression, want the last "by", so we reverse
            words = code_str.split()
            words.reverse()
            by_idx = words.index("by") + 1
            words.reverse()
            words.insert(by_idx, measurement_word)
            variations.append(" ".join(words))

        # "General" case is just put the word right before the brackets, since
        # they're typically  just units
        elif bracketed_text is not None:
            variations.append(
                code_str[:bracketed_text.span()[0]].strip() + " " + \
                    measurement_word + " " + bracketed_text.group(0).strip() + \
                        " " + code_str[bracketed_text.span()[1]:].strip()
            )
            
        # Without brackets, it doesn't matter where, so just throw it at the end
        else:
            variations.append(code_str.strip() + " " + measurement_word)

    return variations


def get_modality_variations(code_str: str, system_axis: str) -> typing.List[str]:
    """
    Given a LOINC code string and its associated system axis, generates a list
    of variations on that code string, each with a modified "modality" element.
    Production data shows that one of the most common ways that nonstandard
    codes are reported is by moving the modality of a test around in the code
    string, or replacing it entirely. The four variations of modality text
    this function generates allow us to capture the most common ways that labs
    tend to send altered data.

    :param code_str: The text string of a LOINC name variant.
    :param system_axis: The system axis of the LOINC code proper.
    :returns: A list of variations on the supplied code string with the 
      modality element altered in one or more ways.
    """
    variations = []
    modality = _find_system_modality(
        code_str, system_axis, LOINC_ENHANCEMENTS, include_parens=True, include_preposition=True
    )
    if modality is not None:
        # Version 1: Move the whole unit to the front but drop prepositions
        variant = apply_syntax_post_processing(modality[0]).strip() + \
            " " + code_str[:modality[1]].strip() + \
                " " + code_str[modality[2]:].strip()
        variations.append(variant.strip())
    
    # We re-find the modality here because the first copy had the preposition 
    # in the string, so this allows us to chunk around that and still maintain
    # grammatical structure
    modality = _find_system_modality(code_str, system_axis, LOINC_ENHANCEMENTS)
    if modality is not None:
        # Version 2: Replace the modality with a different one from within the
        # appropriate axis dictionary
        i = 0
        axis_swap = modality[0]
        while i < MAX_NUM_AXIS_REPLACEMENT_TRIES and axis_swap == modality[0]:
            i += 1
            axis_swap = _choose_from_loinc_axis(system_axis, LOINC_ENHANCEMENTS)
        if axis_swap != "" and axis_swap != modality[0]:
            variant = code_str[:modality[1]].strip() + " " + axis_swap + \
                " " + code_str[modality[2]:].strip()
            variations.append(variant.strip())

        # Version 3 (Special): If the modality is one of the "Big Three", 
        # replace it with a different one
        if modality[0] in BIG_THREE_LIQUID_MODALITIES:
            swap_candidates = [
                c for c in BIG_THREE_LIQUID_MODALITIES if c != modality[0]
            ]
            new_modality = random.choice(swap_candidates)
            variant = code_str[:modality[1]].strip() + " " + new_modality + \
                " " + code_str[modality[2]:].strip()
            variations.append(variant.strip())

        # Version 4 (Special): If the system is a known POC system, replace
        # the modality with "Whole Blood"
        if system_axis in POC_SYSTEMS:
            variant = code_str[:modality[1]].strip() + " Whole Blood " + \
                code_str[modality[2]:].strip()
            variations.append(variant.strip())

    return variations


def get_parens_variations(code_str: str) -> typing.List[str]:
    """
    Given a LOINC code string, generates variants of the string with any
    parenthetical groups (parentheses and the text they enclose) either
    wholly deleted, or turned into a trailing acronym. These modes of
    using parentheses are derived from trends in how vendors often 
    communicate code strings.

    :param code_string: The text string of a LOINC name variant.
    :returns: A list of variations on the string with parenthetical 
      groups modified as appropriate.
    """
    variations = []
    parens_text = PARENTHESES_TEXT.search(code_str)
    if parens_text is not None:
        # Version 1: Delete the whole chunk
        variations.append(PARENTHESES_TEXT.sub('', code_str).strip())
        # Version 2: Check if parenthetical is a trailing acronym
        # If it is, remove the expanded words and just keep the acronym
        possible_acronym = _parenthetical_is_trailing_acronym(parens_text, code_str)
        if possible_acronym is not None:
            variations.append(
                code_str.replace(possible_acronym, '').replace('(', '').replace(')', '').strip()
            )
    return variations


def get_q_variations(code_str: str) -> typing.List[str]:
    """
    Given a LOINC code string, generates variations of the code string with
    its "Q-Group" expanded. A Q-Group is a text chunk of the form "Ql OR Qn"
    followed by a parenthetical with a liquid modality in it, like "(U)" or
    "(Ser/Plas)". Analysis of production data has determined these can be
    expanded to include full modalities, the full quantitative or qualitative
    string, or both.

    :param code_str: The text of the LOINC code's name variant.
    :returns: A list of any generated q-group expansions.
    """
    variations = []
    q_group = Q_GROUP.search(code_str)
    if q_group is not None:
        modality = ""
        q_text = q_group.group(0)
        # First identify what system modality is in the parens
        if "S/P/Bld" in q_text or "Ser/Plas/Bld" in q_text:
            modality = random.choice(BIG_THREE_LIQUID_MODALITIES)
        elif "S/P" in q_text or "Ser/Plas" in q_text:
            modality = random.choice(["Serum", "Plasma", "Serum or Plasma"])
        elif "S" in q_text or "Ser" in q_text:
            modality = "Serum"
        elif "P" in q_text or "Plas" in q_text:
            modality = "Plasma"
        elif "Bld" in q_text or "Blood" in q_text:
            modality = "Blood"
        elif "U" in q_text or "Ur" in q_text:
            modality = "Urine"
        
        # Version 1: The whole q_group chunk is replaced with the modality
        v1 = code_str[:q_group.span()[0]] + modality + " " + \
            code_str[q_group.span()[1] + 1:]
        variations.append(v1.strip())
        # Version 2: Individually, the Q factor and the modality are expanded
        q_factor = ""
        if q_text.startswith("Ql"):
            q_factor = "Qualitative"
        elif q_text.startswith("Qn"):
            q_factor = "Quantitative"
        v2 = code_str[:q_group.span()[0]] + q_factor + " " + modality + \
            " " + code_str[q_group.span()[1] + 1:]
        variations.append(v2.strip())
    
    return variations


def _allocate_generated_loincs_to_training_arrays(
        code_string_base_name: str,
        generated_loincs: typing.List[str],
        search_training_array: typing.List[str],
        reranker_training_array: typing.List[str],
        validation_array: typing.List[str],
    ) -> typing.Tuple[typing.List, typing.List, typing.List]:
    """
    Once a LOINC code name variant has had multiple synthetic variations
    generated, those variant examples must be distributed across different
    model performance tasks, including training, reranking, and validation.
    Discretely separating generated examples in this way ensures that no
    data set has any overlap with any other, while also ensuring 
    comprehensive representation of LOINC codes across modeling tasks. This
    function assigns a collection of synthetically generated LOINC strings
    to the three modeling tasks highlighted above, storing each in a list
    of tuples that pair the variant with the original code text, so that
    those lists can be incrementally grown by future LOINC allocations.

    :param code_string_base_name: The original, unaltered LOINC code text
      we started with, before any synthetic modification.
    :param generated_loincs: A list of all the synthetically generated 
      variants associated with this particular original code text.
    :param search_training_array: The incrementally-built list in which
      we're storing the synthetic examples that will be used to fine-
      tune the model's nearest neighbor search.
    :param reranker_training_array: The incrementally-built list in which
      we're storing the synthetic examples that will be used to fine-
      tune the model's reranker.
    :param validation_array: The incrementally-built list in which we're
      storing the synthetic examples that will be used to evaluate the
      model's overall standardization performance.
    :returns: A tuple with the three lists and their new appended elements.
    """
    # Priority order for each allocation will be:
    # Validation first, then search training, then reranker training
    random.shuffle(generated_loincs)
    if len(generated_loincs) > 0:
        validation_array.append((code_string_base_name, generated_loincs[0]))
        remaining_examples = len(generated_loincs) - 1
        if remaining_examples > 0:
            allocate_to_search = math.ceil(float(remaining_examples) / 2.0)
            for i in range(1, 1 + allocate_to_search):
                search_training_array.append(
                    (code_string_base_name, generated_loincs[i])
                )
            if remaining_examples - allocate_to_search > 0:
                for j in range(1 + allocate_to_search, len(generated_loincs)):
                    reranker_training_array.append(
                        (code_string_base_name, generated_loincs[j])
                    )
    return search_training_array, reranker_training_array, validation_array


def _choose_and_apply_heuristics(code_str: str, property_axis: str, system_axis: str) -> str:
    """
    Given a LOINC code string (which should be either an LCN, DN, or CN, if
    using them) and the corresponding property and system axes for the code,
    determine which semantic variation heuristics can be applied to the code
    and execute them. A semantic variation heuristic is valid for a code
    if the heuristic can generate a new, modified form of the input. Note
    that short names should not be supplied as input to this function, as
    they lack the structure and content needed for semantic variation.

    :param code_str: The text of a LOINC code name variant.
    :param property_axis: The Property axis of the LOINC code proper.
    :param system_axis: The System axis of the LOINC code proper.
    :returns: A new version of the code string with variation applied, or
      the empty string if no variation can be performed.
    """
    eligible_heuristics = _determine_eligible_pattern_heuristics(
        code_str, property_axis, system_axis
    )
    if len(eligible_heuristics) == 0:
        return ""

    heuristics_to_perform = []
    if len(eligible_heuristics) == 1:
        heuristics_to_perform.append(eligible_heuristics[0])
    else:
        heuristics_to_perform = random.sample(eligible_heuristics, 2)
    modified_code = _clean_unpaired_parens(code_str)

    for h in heuristics_to_perform:
        if h == "measurement":
            variations = get_measurement_variation(modified_code, property_axis)
            # At each stage, if we can't generate real variations due to a
            # property error, at least use the previous step to keep future
            # heuristics in order
            if len(variations) == 0:
                variations.append(modified_code)
            modified_code = random.choice(variations)
        if h == "q group":
            variations = get_q_variations(modified_code)
            if len(variations) == 0:
                variations.append(modified_code)
            modified_code = random.choice(variations)
        if h == "modality":
            variations = get_modality_variations(modified_code, system_axis)
            if len(variations) == 0:
                variations.append(modified_code)
            modified_code = random.choice(variations)
        if h == "parens":
            variations = get_parens_variations(modified_code)
            if len(variations) == 0:
                variations.append(modified_code)
            modified_code = random.choice(variations)
        if h == "brackets":
            variations = get_bracket_variations(modified_code)
            if len(variations) == 0:
                variations.append(modified_code)
            modified_code = random.choice(variations)
    
    return modified_code


def _choose_and_apply_post_processing(
        code_str: str,
        fsn: str,
        system_axis: str,
        loinc_enhancements: dict,
        base_options: typing.List[typing.Literal[
            "poc",
            "modality",
            "delimiter",
            "truncation",
            "syntax",
            "pound",
            "deletion",
            "dot"
        ]]
    ) -> str:
    """
    Given a synthetically generated LOINC code string, this function
    identifies valid post-processing functions which could be applied
    to the string, and then randomly applies up to 2 of them. A post-
    processing function is valid if applying it would result in an actual
    change to the code string (e.g. pound sign variation for code strings
    containing '[#/volume]'). If fewer than 2 post processors can be
    applied, all found PPs are executed. If more than 2 are identified,
    then 2 are randomly selected.

    :param code_str: The text string for a LOINC code name variant.
    :param fsn: The fully-specified name for the LOINC code.
    :param system_axis: The System axis of the LOINC code proper.
    :param loinc_enhancements: A dictionary of LOINC-related words, including
      abbreviations and acronyms, that can be searched via axes.
    :param base_options: The starting list of eligible post processors for
      this code string. Some name variants, like LCN, will have all options
      available by default, but others, like short name, will not be
      able to use them all.
    :returns: A new string with all valid and selected post processing 
      applied.
    """
    eligible_post_processing = _determine_eligible_post_processing(
        code_str, system_axis, loinc_enhancements, base_options
    )

    if len(eligible_post_processing) == 0:
        return ""
    
    processed_code = _clean_unpaired_parens(code_str)
    outer_handling_method = random.choice(["drop", "count"])

    # Desired state is to have two or more forms of post-processing available,
    # but many codes won't have that as an option. If there's just one, we do
    # it, but if not, no variation to apply.
    if len(eligible_post_processing) == 1:
        pps = [eligible_post_processing[0]]
    
    # Grab two different ones; there's no incompatible combinations so any
    # two will work
    else:
        pps = random.sample(eligible_post_processing, 2)

    # We do have to apply these in a certain order, since some processes
    # rely on other information (e.g. there could be pound signs in a 
    # modality, or there could delimiters in a word marked for deletion)
    if 'pound' in pps:
        processed_code = apply_pound_sign_post_processing(
            processed_code, outer_handling_method=outer_handling_method
        )
    if 'modality' in pps:
        processed_code = apply_modality_drop_post_processing(
            processed_code, system_axis=system_axis, loinc_enhancements=LOINC_ENHANCEMENTS
        )
    if 'syntax' in pps:
        processed_code = apply_syntax_post_processing(processed_code)
    if 'dot' in pps:
        processed_code = apply_dot_flip_post_processing(processed_code)
    if 'poc' in pps:
        processed_code = apply_point_of_care_post_processing(processed_code)
    if 'delimiter' in pps:
        processed_code = apply_delimiter_post_processing(processed_code)
    if 'deletion' in pps:
        processed_code = apply_deletion_post_processing(
            processed_code, fsn=fsn, loinc_enhancements=LOINC_ENHANCEMENTS
        )
    if 'truncation' in pps:
        processed_code = apply_truncation_post_processing(processed_code)

    return processed_code


def _codestring_is_valid_candidate(
        code_str: str | None, original_code: str
    ) -> bool:
    """
    Simple function for identifying whether a newly generated
    synthetic code is a valid candidate to represent its original.
    Valid means it's non-null, non-empty, and non-equal.

    :param code_str: The synthetically generated code string.
    :param original_code: The text of the LOINC code's original name
      variant.
    :returns: A boolean indicating whether the synthetic example is
      a valid training example.
    """
    return code_str is not None and \
        code_str != "" and code_str != original_code


def _determine_eligible_pattern_heuristics(
        code_str: str, property_axis: str, system_axis: str
    ) -> typing.List[str]:
    """
    Given a LOINC code string and its corresponding property and system
    axes, identify the kinds of semantic variation that can be applied
    to it, based on the text elements that are present. For example,
    Q-Group variation could be applied to a short name containing "Ql (U)"
    but not to a long common name using the broader text "in Urine."

    :param code_str: The text string of a LOINC code name variant.
    :param property_axis: The Property axis of the LOINC code proper.
    :param system_axis: The System axis of the LOINC code proper.
    :returns: A list of string short-hands for valid forms of semantic
      variation for this code string.
    """
    eligible_heuristics = []
    for h in BASE_HEURISTIC_OPTIONS:
        if h == "measurement":
            measurement_word = _get_measurement_unit_word(code_str, property_axis)
            if measurement_word != "":
                eligible_heuristics.append(h)
        if h == "q group":
            q_group = Q_GROUP.search(code_str)
            if q_group is not None:
                eligible_heuristics.append(h)
        if h == "modality":
            modality = _find_system_modality(code_str, system_axis, LOINC_ENHANCEMENTS)
            if modality is not None:
                eligible_heuristics.append(h)
        if h == "parens":
            parens_text = PARENTHESES_TEXT.search(code_str)
            if parens_text is not None:
                eligible_heuristics.append(h)
        if h == "brackets":
            bracketed_text = BRACKETED_TEXT.search(code_str)
            if bracketed_text is not None:
                eligible_heuristics.append(h)
    return eligible_heuristics


def _get_single_word_method(code_str: str) -> typing.Tuple[str, ]:
    """
    Given a LOINC code string, determines if the included method-text in the
    string can be represented as a "one-word test" (for example, condensing
    'by screen method' into 'Screening.') This substitution is a known
    template among some eCR vendors.

    :param code_str: The string text of a LOINC code name variant.
    :returns: A tuple containing the one-word method descriptor (or "", 
      if one could not be identified) as well as the index in the
      code string where the original method text occurs (so that it
      can be validated or replaced).
    """
    # Use spaces here to make sure we don't capture prefixes or suffixes
    if " by " in code_str:
        words = code_str.split()
        # We only want method clauses that end codes, so we need to find the
        # last instance of "by", which we can do by reversing the order
        words.reverse()
        # We want the "by" included because it will also get replaced
        by_idx = words.index("by") + 1
        method_clause = words[:by_idx]
        method_clause.reverse()
        method_clause = " ".join(method_clause)
        if method_clause.lower() in SINGLE_WORD_METHOD_MAPPINGS:
            method_mapping = SINGLE_WORD_METHOD_MAPPINGS[method_clause.lower()]
            return (method_mapping, by_idx * -1)
    return ("", None)


def _get_measurement_unit_word(
        code_str: str, property_axis: str, return_symbol: bool = False
    ) -> str:
    """
    Given a LOINC code string and its corresponding property axis, determines
    an appropriate word that can be used to describe the measurement type or
    unit of the code's hypothetical result. For example, a code that includes
    the text 'by calculation' would have a result described as a 'Determination.'
    A code string that had a '[Presence]' of a compound or organism would
    have a result described as a 'Detection.' This "measurement-style" word
    is used in a number of known eCR vendor templates for lab description,
    so being able to reverse engineer them from code strings allows us to 
    train on that knowledge.

    :param code_str: The LOINC code string to determine the word for.
    :param property_axis: The Property axis of the LOINC code proper.
    :param return_symbol: Optionally, whether to return the symbolic 
      representation of the measurement word (% for percentage, for 
      example), if applicable.
    :returns: The single measurement-descriptive word for the code string.
    """
    if "by calculation" in code_str.lower():
        return "Determination"
    if "in specimen" in code_str.lower():
        return "Detected"
    
    # Some codes don't have a meaningful property specified, so just treat
    # those as blank
    if property_axis is None:
        property_axis = ""

    if property_axis.endswith("Rto"):
        return "Ratio"
    if property_axis.endswith("Fr") and property_axis != "MFr":
        if return_symbol:
            return "%"
        else:
            return random.choice(["Percent", "Percentage"])
    code_has_dot_chunk = apply_dot_flip_post_processing(code_str) != ""
    bracketed_text = BRACKETED_TEXT.search(code_str)
    if bracketed_text is not None:
        bracket_text_raw = bracketed_text.group(0).lower()
        if "presence" in bracket_text_raw:
            return "Detection"
        if "#" in bracket_text_raw or property_axis == "NCnc":
            return random.choice(["Absolute", "Count"])
        
        if not code_has_dot_chunk:
            # Little bit of repeated code here, but codes with "moles" *always*
            # get labeled 'measurement,' so we can't put this with the MCnc 
            # check below because a LOINC could have property MCnc, have moles
            # in brackets, and then get randomly assigned "level"
            if "moles" in bracket_text_raw:
                return "Measurement"
            if property_axis == "MCnc" or "mass" in bracket_text_raw:
                return random.choice(["Measurement", "Level", "Result"])
            if "MCnc" in property_axis:
                return "Measurement"
        
    elif property_axis == "MFr" and not code_has_dot_chunk:
        return "Measurement"
    
    return ""


if __name__ == "__main__":

    random.seed(1246)

    # Read the SNOINC data and ditch the first row headers
    with open(SNOINC_DATA_FILE, 'r',encoding="utf-8") as fp:
        data = fp.readlines()
    data = data[1:]

    # We'll track and accumulate examples for each of search training, 
    # reranker training, and testing all at once, so that we can
    # distribute some examples of each code into each bucket
    search_train_lcns = []
    reranker_train_lcns = []
    validation_lcns = []
    search_train_cns = []
    reranker_train_cns = []
    validation_cns = []
    search_train_dns = []
    reranker_train_dns = []
    validation_dns = []
    # There aren't enough short names generated to randomize these
    # as we go, so we'll do it at the end
    sns = []

    for row in data:
        r = row.split("|")
        # Skip any malformed rows
        if len(r) < 6:
            continue

        loinc_code, lab_type, property_axis, time_axis, system_axis, scale_axis, \
            method_axis, class_type, short_name, long_common_name, display_name, \
                fully_specified_name, consumer_name = r[0], r[1], r[2], r[3], r[4], \
                r[5], r[6], r[7], r[8], r[9], r[10], r[13], r[14]
        
        # LOINC has a special property called {Measurement} which groups together
        # related quantitative values; need to expand this if it's present
        if property_axis is None:
            property_axis = ""
        if property_axis.strip() == "{Measurement}":
            property_axis = _expand_measurement_property(property_axis)

        # Structurize the code for more effective processing
        structured_loinc: schemas.LoincStruct = schemas.LoincStruct(
            long_common_name = long_common_name.strip(),
            short_name = short_name.strip(),
            display_name = display_name.strip(),
            consumer_name = consumer_name.strip(),
            fully_specified_name = fully_specified_name.strip(),
            lab_type = lab_type.strip().lower(),
            class_type = class_type.strip(),
            property = property_axis.strip() if _axis_is_valid(property_axis.strip()) else None,
            time = time_axis.strip() if _axis_is_valid(time_axis.strip()) else None,
            system = system_axis.strip() if _axis_is_valid(system_axis.strip()) else None,
            scale = scale_axis.strip() if _axis_is_valid(scale_axis.strip()) else None,
            method = method_axis.strip() if _axis_is_valid(method_axis.strip()) else None
        )

        # For each name variant, appropriately allocate synthetic examples
        # between various types of training and testing
        synthetic_examples = create_synthetic_examples_for_code(structured_loinc)
        search_train_lcns, reranker_train_lcns, validation_lcns = \
            _allocate_generated_loincs_to_training_arrays(
                structured_loinc.long_common_name,
                synthetic_examples["long_common_name"],
                search_train_lcns,
                reranker_train_lcns,
                validation_lcns
            )
        search_train_dns, reranker_train_dns, validation_dns = \
            _allocate_generated_loincs_to_training_arrays(
                structured_loinc.display_name,
                synthetic_examples["display_name"],
                search_train_dns,
                reranker_train_dns,
                validation_dns
            )
        if INCLUDE_CN_IN_FINAL_OUTPUT:
            search_train_cns, reranker_train_cns, validation_cns = \
                _allocate_generated_loincs_to_training_arrays(
                    structured_loinc.consumer_name,
                    synthetic_examples["consumer_name"],
                    search_train_cns,
                    reranker_train_cns,
                    validation_cns
                )
        # We'll have to randomize and divide up short names at the end,
        # there just aren't enough to apportion for each code
        for ex_string in synthetic_examples["short_name"]:
            sns.append( (structured_loinc.short_name, ex_string) )
    
    # Now we'll divide up short names 50-30-20 across training and testing
    random.shuffle(sns)
    search_idx = math.ceil(float(len(sns)) / 2.0)
    search_train_sns = sns[:search_idx + 1]
    reranker_idx = math.ceil(float(len(sns) - search_idx) * 0.6)
    reranker_train_sns = sns[search_idx + 1 : reranker_idx + 1]
    validation_sns = sns[reranker_idx + 1:]

    # Finally, we write all training files and wrap up this ungodly process
    with open(SEARCH_TRAINING_OUT_FILE, 'w') as fp:
        all_examples = search_train_lcns + search_train_sns + \
            search_train_dns
        if INCLUDE_CN_IN_FINAL_OUTPUT:
            all_examples.extend(search_train_cns)
        random.shuffle(all_examples)
        for ex in all_examples:
            fp.write(ex[0] + "|" + ex[1] + "\n")
    with open(RERANKER_TRAINING_OUT_FILE, 'w') as fp:
        all_examples = reranker_train_lcns + reranker_train_sns + \
            reranker_train_dns
        if INCLUDE_CN_IN_FINAL_OUTPUT:
            all_examples.extend(reranker_train_cns)
        random.shuffle(all_examples)
        for ex in all_examples:
            fp.write(ex[0] + "|" + ex[1] + "\n")
    with open(TESTING_OUT_FILE, 'w') as fp:
        all_examples = validation_lcns + validation_sns + \
            validation_dns
        if INCLUDE_CN_IN_FINAL_OUTPUT:
            all_examples.extend(validation_cns)
        random.shuffle(all_examples)
        for ex in all_examples:
            fp.write(ex[0] + "|" + ex[1] + "\n")