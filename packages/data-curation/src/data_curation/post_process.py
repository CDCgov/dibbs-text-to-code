"""data_curation.post_process
~~~~~~~~~~~~~~~~~~~~~~~~~

This module contains a suite of functions used for post-processing a
synthetically-generated LOINC code string. These post-processing functions
offer an additional means (besides build patterns and primary variations)
of introducing small syntactical and string-based changes to produce
richer training examples.
"""

import math
import random
import re
import typing

from data_curation.loinc_utils import LOINC_PREPOSITIONS
from data_curation.loinc_utils import _find_system_modality
from data_curation.loinc_utils import _get_component_axis_from_fsn

# Derived from rule analysis
MAX_CHARS_FOR_TRUNCATION = 85
LOINC_DELIMITERS = ["+", "&"]
# The "/" character in standard LOINC is not used to conjoin two related
# things (e.g. 'lymphocytes' and 'neutrocytes'), but might be used this
# way in a supplied input (such as "lymphocytes/leukocytes"), so this
# needs to be a valid "change to" target even if not a "change from"
EXPANDED_LOINC_DELIMITERS = LOINC_DELIMITERS + ["/"]


def apply_deletion_post_processing(code_str: str, **kwargs) -> str:
    """Applies random word deletion to a given code string, leaving intact the
    core concept of the string (via the Component axis). This ensures that
    any words needed for systematic identification are left in place (e.g.
    in the phrase Red Blood Cell, we don't accidentally delete Blood or Red).
    The number of words deleted from the string is automatically deduced from
    the number of non-Component words present in the code.

    :param code_str: The text of the LOINC code string.
    :param fsn: The fully specified name of the LOINC code in question, which
      must be passed-in as a kwarg.
    :param loinc_enhancements: A dictionary of abbreviations and acronyms for
      LOINC axis words, which must be passed-in as a kwarg.
    :returns: A copy of the string with some words randomly removed.
    """
    # First, we need to identify the core component of the string
    fsn = kwargs["fsn"]
    loinc_enhancements = kwargs["loinc_enhancements"]
    component = _get_component_axis_from_fsn(fsn)
    component_struct = loinc_enhancements[component.lower()]
    component_choices = component_struct["abbrv"] + component_struct["synonyms"]
    component_choices.append(component)

    component_idx = -1
    present_component = None
    for cc in component_choices:
        idx = code_str.find(cc)
        # Need the length check here because we want to match the whole name
        # of a component if it's present, not just an acronym--e.g. if we break,
        # we'd miss a modality of 'fentaNYL' by just matching 'fent'
        if idx != -1 and (present_component is None or len(cc) > len(present_component)):
            component_idx = idx
            present_component = cc

    # Now, convert the string index into an appropriate span of array
    # indices that we'll exclude from deletion candidates
    idxs_to_exclude = []
    if component_idx != -1:
        preceding_words = code_str[:component_idx].strip().split()
        # First word of the component is the length of the preceding array,
        # due to 0-indexing of strings, so just find the length of the
        # form of component that's present and exclude those
        idxs_to_exclude = list(
            range(
                len(preceding_words), len(preceding_words) + len(present_component.strip().split())
            )
        )

    # With the component identified, now we can determine our number of
    # deletions and where they're allowed to come from
    words = code_str.split()
    deletion_eligible_idxs = [i for i in range(len(words)) if i not in idxs_to_exclude]
    # 1-4 words del 1, 5-8 words del 2, 9-12 words del 3, etc.
    num_deletions = math.ceil(float(len(deletion_eligible_idxs)) / 4.0)
    idxs_to_delete = random.sample(deletion_eligible_idxs, num_deletions)
    return " ".join([w for i, w in enumerate(words) if i not in idxs_to_delete])


def apply_delimiter_post_processing(code_str: str, **kwargs) -> str:
    """Given a code-string, changes each conjoining delimiter into another,
    different delimiter. Conjoining delimiters are those that combine two
    or more concepts (e.g. '+' and '&').

    :param code_str: The code string in which to change the delimiters.
    :returns: A new string with delimiters swapped.
    """
    new_code_str = ""
    # Python strings are immutable, so we'll have to build a new string
    # character by character
    for char in code_str:
        if char in LOINC_DELIMITERS:
            other_delimiters = [d for d in EXPANDED_LOINC_DELIMITERS if d != char]
            new_delimiter = random.choice(other_delimiters)
            new_code_str += new_delimiter
        else:
            new_code_str += char
    return new_code_str


def apply_dot_flip_post_processing(code_str: str, **kwargs) -> str:
    """Performs "dot notation" inversion on a given code string, if there are any
    dot-groups present. A dot-group is a word sequence of the form "X.Y", and
    the dot inversion of this group is the sequence "Y X". This typically occurs
    with adjectival descriptors attached directly to concept nouns, such as
    "protein.total" (which would become "total protein").

    :param code_str: The code string whose dot-groups to invert.
    :returns: A new copy of the code string with dots inverted. If the code
      string had no dot groups, the empty string is returned instead.
    """
    dot_chunk = re.search(r"\w+\.\w+", code_str)
    if dot_chunk is not None:
        chunked_words = dot_chunk.group(0).split(".")
        chunked_words.reverse()
        flipped_text = " ".join(chunked_words)
        chunk_start, chunk_end = dot_chunk.span()[0], dot_chunk.span()[1]
        return code_str[:chunk_start] + flipped_text + code_str[chunk_end:]
    return ""


def apply_modality_drop_post_processing(code_str: str, **kwargs) -> str:
    """Given a code string with a valid system modality, removes the modality and
    any associated parentheses or prepositions from the string to create a
    "lab simplified" version of the code. If the given code string does not
    contain a modality, the original, unmodified code string is returned.

    :param code_str: The code string from which to drop the modality.
    :param system_axis: The System axis of the LOINC code, which must be
      passed-in as a kwarg.
    :param loinc_enhancements: A dictionary of axis-expanded LOINC words,
      which must be passed-in as a kwarg.
    :returns: A copy of the code string with its modality dropped, or the
      original code string if there was no modality.
    """
    loinc_enhancements = kwargs["loinc_enhancements"]
    system_axis = kwargs["system_axis"]
    system_modality = _find_system_modality(
        code_str, system_axis, loinc_enhancements, include_parens=True, include_preposition=True
    )
    if system_modality is not None:
        dropped = (
            code_str[: system_modality[1]].strip() + " " + code_str[system_modality[2] :].strip()
        )
        # Possible that the modality was at the end of the code string,
        # so need one final `.strip()` just in case
        return dropped.strip()
    return code_str


def apply_point_of_care_post_processing(code_str: str, **kwargs) -> str:
    """Simple post-processor to create a "Point of Care" version of a code."""
    return "POC " + code_str


def apply_pound_sign_post_processing(code_str: str, **kwargs) -> str:
    """Given a code string, this function transforms all pound signs '#'
    according to whether or not those pound signs are enclosed by
    parentheses (inner #). Any pounds outside of parentheses are considered
    outer signs. To run correctly, this function **requires** that all
    unpaired parentheses have already been removed.

    :param code_str: The text of the LOINC code string to modify.
    :param outer_handling_method: A string literal, either 'drop' or 'count',
      that governs how any #'s outside of parenthetical containment are
      handled. 'Drop' removes them, 'count' replaces them with the literal
      word "count." Must be passed-in as a kwarg.
    :returns: The code string with pound signs appropriately replaced.
    """
    outer_handling_method = kwargs["outer_handling_method"]  # drop or count
    pounds_idxs = []
    push_chars, pop_chars = "([{<", ")]}>"

    currently_in_brackets = False
    for i, c in enumerate(code_str):
        if c in push_chars:
            currently_in_brackets = True
        elif c in pop_chars:
            currently_in_brackets = False
        elif c == "#":
            pounds_idxs.append((i, currently_in_brackets))

    pounds_idxs.sort(key=lambda x: x[0], reverse=True)
    result_string = code_str
    for pound_sign in pounds_idxs:
        pidx = pound_sign[0]
        if pound_sign[1]:
            to_write = "Number"
        elif outer_handling_method == "drop":
            to_write = ""
        elif outer_handling_method == "count":
            to_write = "Count"
        result_string = result_string[:pidx] + to_write + result_string[pidx + 1 :]

    return result_string.strip()


def apply_syntax_post_processing(code_str: str, **kwargs) -> str:
    """Simple function that removes commas and all non-lab prepositions from a
    code string.
    """
    code_str = code_str.replace(",", "")
    code_str = " ".join([w for w in code_str.split() if w not in LOINC_PREPOSITIONS])
    return code_str


def apply_truncation_post_processing(code_str: str, **kwargs) -> str:
    """Simple character-length enforcement of a given code-string."""
    return code_str[: min(MAX_CHARS_FOR_TRUNCATION, len(code_str))]


def _determine_eligible_post_processing(
    code_str: str,
    system_axis: str,
    loinc_enhancements: dict,
    base_options: list[
        typing.Literal[
            "poc", "modality", "delimiter", "truncation", "syntax", "pound", "deletion", "dot"
        ]
    ],
) -> list[str]:
    """Determines which types of post-processing can be successfully applied to
    a given code string. A post processing form is valid if it would result in
    a change to the input, e.g. pound sign post processing could not be applied
    to a code string with no '#' characters. The collection of valid, eligible
    processing choices is build up into a list, which is returned.

    :param code_str: The text of the LOINC code string to determine eligible
      post-processing options for.
    :param system_axis: The system axis of the LOINC code proper.
    :param loinc_enhancements: A dictionary of abbreviations and acronyms for
      LOINC-related words.
    :param base_options: A list of one or more post-processing options to
      consider for this code-string. Useful if passing in a code string that
      you already know will not meet certain post-processing criteria.
    :returns: A list of valid, eligible post-processing options.
    """
    options = []
    for o in base_options:
        # Always eligible since it's just prepending
        if o == "poc":
            options.append(o)

        # Eligible any time there's a modality in the code
        if o == "modality":
            if _find_system_modality(code_str, system_axis, loinc_enhancements) is not None:
                options.append(o)

        # Eligible as long as at least one delimiter exists
        if o == "delimiter":
            for c in LOINC_DELIMITERS:
                if c in code_str:
                    options.append(o)
                    break

        # Eligible if the string is long enough to be truncated
        if o == "truncation" and len(code_str) > 85:
            options.append(o)

        # Eligible if the code contains commas or prepositions
        if o == "syntax":
            contains_preposition = False
            for w in code_str.split():
                if w in LOINC_PREPOSITIONS:
                    contains_preposition = True
                    break
            if "," in code_str or contains_preposition:
                options.append(o)

        # Eligible if there's a pound sign in the code string
        if o == "pound":
            if "#" in code_str:
                options.append(o)

        # Eligible as long as the code has at least two words, so we don't
        # delete everything present
        if o == "deletion":
            if len(code_str.split()) >= 2:
                options.append(o)

        # Eligible as long as the code has a dote notation expression
        if o == "dot":
            dot_chunk = re.search(r"\w+\.\w+", code_str)
            if dot_chunk is not None:
                options.append(o)

    return options
