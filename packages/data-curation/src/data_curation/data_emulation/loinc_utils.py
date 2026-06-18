"""
data_curation.loinc_utils
~~~~~~~~~~~~~~~~~~~~~~~~~

This module contains a number of helper functions designed to be used as
part of synthetic data generation. These functions are used both when
generating variations and applying post-processing.
"""


import random
import re
from typing import Tuple

from utils.regex_patterns import MULTIPLE_SPACE


LOINC_PREPOSITIONS = ["in", "of", "by", "for", "at", "per", "with", "on", "via", "from", "into", "to"]


def scramble_word_order(
    text: str,
    max_perms: int,
    min_perms: int = 1,
) -> str:
    """
    Scrambles the order of words in the input text by moving a specified
    number of words to new positions.

    :param text: The input text to scramble.
    :param max_perms: The maximum number of words to move.
    :param min_perms: The minimum number of words to move.
    :return: The text with words scrambled.
    """
    words = text.split()
    if len(words) < 2:
        return text

    # Ensure max_perms does not exceed the number of words
    num_perms = min(random.randint(min_perms, max_perms), len(words) - 1)

    # Select unique indices to scramble
    indices_to_move = sorted(random.sample(range(len(words)), num_perms), reverse=True)

    for idx in indices_to_move:
        new_pos = random.choice([i for i in range(len(words)) if i != idx])
        word = words.pop(idx)
        words.insert(new_pos, word)

    return " ".join(words)


def _axis_is_valid(axis: str | None) -> bool:
    """
    Determines whether a given string is a valid candidate for a LOINC
    axis. A string might be a valid axis if it is non-null, not empty,
    and is not a formatting dash. Note that this function does not 
    determine whether the given string is a proper axis, merely that 
    its formatting doesn't disqualify it.

    :param axis: The axis to determine the validity of.
    :returns: A boolean indicating whether the axis is valid.
    """
    if axis is not None:
        if axis != "" and axis != "-":
            return True
    return False


def _choose_from_loinc_axis(axis: str | None, loinc_enhancements: dict) -> str:
    """
    Given one of the six LOINC axes and a dictionary of axis-based enhancements,
    randomly selects one possible replacement for the axis from its dictionary
    entry. This choice includes both abbreviations and synonyms. If the axis
    is invalid, has no enhancement entry, or has no related words, the empty
    string is returned.

    :param axis: The LOINC axis to search.
    :param loinc_enhancements: The dictionary of LOINC-axis-keywords to sets
      of abbreviations and enhancements related to that particular axis.
    :returns: The randomly chosen axis-word, or the empty string.
    """
    if axis is None or axis == "":
        return ""
    try:
        axis_struct = loinc_enhancements[axis.lower()]
        all_choices = axis_struct["abbrv"] + axis_struct["synonyms"]
        if len(all_choices) > 0:
            return random.choice(all_choices)
    except KeyError:
        # Some LOINCs have axes that don't resolve to real entities
        # E.g., the system property {nursing unit} has no expandable
        # systems it applies to, it's just a random string (see
        # part specification here https://loinc.org/LP34963-6).
        pass
    return ""


def _clean_unpaired_parens(code_string: str) -> str:
    """
    Removes any unpaired "bracketing characters" that are either openers
    or closers from the string. For purposes of this function, bracketing
    characters are any of (), [], {}, or <>. Compresses nested bracketing
    by looking for the first instance of a character that would complete
    a found pair. For instance, in the string 

      'blah [blah (blah blah] blah)"

    the brackets would complete before the parentheses, so the parentheses
    would be marked as the unpaired characters and removed. 

    :param code_string: The text of a LOINC code string to clean.
    :returns: The code string with all unpaired bracketing chars removed.
    """
    cleaned_chars = []
    # I laughed when my intro CS professor said I'd one day use a 
    # parens-matching stack algorithm, because little did he know
    # I'd need to repeatedly iterate backwards through my stack.
    bracket_stack = []
    known_deletions = []
    push_chars, pop_chars = "([{<", ")]}>"

    for i, c in enumerate(code_string):
        if c in push_chars:
            bracket_stack.append((i, c))
            cleaned_chars.append((i, c))
        elif c in pop_chars:
            # If there's no opening delimiter, this character is already
            # known to be unpaired
            if len(bracket_stack) > 0:
                # We got schwifty with our push/pop chars--they're symmetric
                would_close_char = push_chars[pop_chars.index(c)]
                # We need to work our way from the end of the stack to the front
                # to find the first instance of a character that would close this.
                # Can't just pop the top of the stack because you could have 
                # something like '[blah ( blah2]', where the paren is actually
                # wrong but the brackets are right.
                paired_opening_idx = -1
                for i in range(len(bracket_stack) -1, -1, -1):
                    if bracket_stack[i][1] == would_close_char:
                        paired_opening_idx = i
                        break
                # We found something would close it, so we need to remove all
                # openers from the stack between the end and that value, because
                # they're now "dead characters" that have already been closed.
                # They can't trigger later closures, because then you could have
                # akward cases like 'a [b ( cde ] f)'.
                if paired_opening_idx != -1:
                    cleaned_chars.append((i, c))
                    for j in range(paired_opening_idx + 1, len(bracket_stack)):
                        known_deletions.append(bracket_stack[j])
                    bracket_stack = bracket_stack[:paired_opening_idx]
        else:
            cleaned_chars.append((i, c))
    
    # Now, any tuples left in the stack are unpaired, so grab the chars
    # in the result we've built up that has the matching index
    bracket_stack = [e[0] for e in bracket_stack + known_deletions]
    cleaned_chars = [t[1] for t in cleaned_chars if t[0] not in bracket_stack]
    cleaned_string = "".join(cleaned_chars)

    # Last step is compressing any double-whitespace characters, since we may
    # have deleted surrounding letters
    cleaned_string = MULTIPLE_SPACE.sub(' ', cleaned_string)
    return "".join(cleaned_string)


def _expand_measurement_property(msmt: str) -> str:
    """
    LOINC has one Part-Code, `{Measurement}` (https://loinc.org/LP447904-6),
    which is designed as a descriptive stand in for multiple equivalent
    values. Since `{Measurement}` itself can't be enhanced as part of a code
    string, this function replaces it where it occurs with a random choice
    from the more specific eligible part codes.

    :param msmt: The Property code to expand.
    :returns: The randomly chosen expansion. If `msmt` is not `{Measurement}`,
      returns `msmt` instead.
    """
    if msmt != "{Measurement}":
        return msmt
    possible_expansions = [
        "ACnc", "AFr", "ARat", "CAct", "CCnc", "CCnt", "CRat", "CSub", "EntLen", \
            "LaCnc", "LnCnc", "Mass", "MCnc", "MCnt", "MRat", "MRto", "MSCnc", \
            "MSRat", "Naric", "NCnc", "NFr", "Prctl", "PrThr", "Ratio", "SatFr", \
            "SCnc", "SCnt", "SRat", "SRto", "Sub", "ThreshNum", "Titr", "TmMCnc"
    ]
    return random.choice(possible_expansions)


def _find_system_modality(
        code_str: str,
        system_axis: str | None,
        loinc_enhancements: dict,
        include_parens: bool = False,
        include_preposition: bool = False
) -> Tuple[str, int, int] | None:
    """
    Given a LOINC code string, this function locates the text in the string
    representing the system modality of the code, if it exists. The modality
    of a LOINC code is the "substance" (often a liquid like Blood or Plasma)
    in which the test was performed. It can be formally defined by the System
    axis property of the LOINC code, but the actual text with which it appears
    might vary, including one or more related names. This function locates
    the maximal group of words that make up the modality so that the whole
    unit can be treated as a group.

    :param code_str: The LOINC code string in which to find the modality.
    :param system_axis: The System property of the LOINC code proper.
    :param loinc_enhancements: A pre-compiled dictionary of abbreviations and
      synonyms for various LOINC axis words.
    :param include_parens: Optionally, whether to include any parentheses 
      that might be surrounding the modality as part of the modality group.
    :param include_preposition: Optionally, whether to include a leading
      preposition as part of the modality group.
    :returns: A Tuple with the found modality string, the character index
      at which the modality string starts within `code_str`, and the index
      at which the modality string ends.
    """
    if system_axis is None or system_axis == "":
        return None
    try:
        system_struct = loinc_enhancements[system_axis.lower()]
        system_choices = system_struct["abbrv"] + system_struct["synonyms"]
        # Add the axis itself becomes it's often the actual modality (i.e. "Urine")
        system_choices.append(system_axis)
        # Some multi-word modalities, especially the Big Three liquids, have nonstandard
        # capitalization throughout--we want to match on any variety but keep the 
        # value that occurs
        if system_axis == "Ser/Plas":
            system_choices.append("Serum or Plasma")
        if system_axis == "Ser/Plas/Bld":
            system_choices.append("Serum, Plasma or Blood")

        modality_idx = -1
        modality = None
        for sc in system_choices:
            idx = code_str.find(sc)
            # Need the length check here because we want to match the whole name
            # of a modality if it's present, not just an acronym--e.g. if we break,
            # we'd miss a modality of 'Urine' by just matching 'Ur'
            if idx != -1 and (modality is None or len(sc) > len(modality)):
                modality_idx = idx
                modality = sc

        if modality is None:
            return None
        
        if include_parens and _substring_is_contained_in_parens(
            code_str, modality_idx, modality_idx + len(modality)
        ):
            return (
                code_str[modality_idx - 1 : modality_idx + len(modality) + 1],
                modality_idx - 1,
                modality_idx + len(modality) + 1
            )

        preceding_word = _get_preceding_word(modality, code_str)
        if include_preposition and preceding_word in LOINC_PREPOSITIONS:
            return (
                code_str[modality_idx - len(preceding_word) - 1 : modality_idx + len(modality)],
                modality_idx - len(preceding_word) - 1,
                modality_idx + len(modality)
            )
        return (modality, modality_idx, modality_idx + len(modality))
    
    # Case where the system is something that doesn't have a UMLS / RELMA
    # mapping like "{Nursing Unit}", which has no valid modal expansions
    except KeyError:
        return None
    

def _get_component_axis_from_fsn(fsn: str | None) -> str:
    """
    Identifies the Component axis of a LOINC code by parsing its Fully-
    Specified Name. The component axis is a field not loaded as part of
    the LOINC API extract, but it is uniquely identified by the FSN.
    This function uses format specifications and edge case knowledge
    to obtain the precise Component of a code.

    :param fsn: The Fully-Specified Name of the LOINC code.
    :returns: The Component axis, as a string.
    """
    if fsn is None:
        return ""
    axis_parts = fsn.strip().split(":")
    # Ordinary case where each part has no other colons
    if len(axis_parts) == 6:
        return axis_parts[0].strip()
    elif len(axis_parts) > 6:
        # Three possibilities: survey question, chem reaction, or solution ratio
        if axis_parts[-1].isdigit() and axis_parts[-2].endswith("1"):
            # This is the case where a blood coagulant or serum ratio is
            # included in the FSN. In this case, we want the normal first
            # portion
            return axis_parts[0].strip()
        elif axis_parts[-2] == "Reaction":
            # Chemical reactions among catalytic agents are denoted with colons
            # In this case, we still just want the first part
            return axis_parts[0].strip()
        else:
            # Some survey questions have a colon in their component axis to group
            # by socioeconomic category
            additional_parts_to_join = len(axis_parts) - 6
            return ":".join(axis_parts[:additional_parts_to_join + 1])
    else:
        return ""
    

def _get_preceding_word(substring: str, string: str) -> str:
    """
    Given a substring contained within another string, this function
    finds and returns the word immediately preceding the substring, if
    it exists.
    """
    substring_idx = string.find(substring)
    if substring_idx != -1:
        preceding_string = string[:substring_idx].strip()
        if preceding_string != "":
            preceding_word = preceding_string.split()[-1]
            return preceding_word
    return ""


def _parenthetical_is_trailing_acronym(
        parenthetical: re.Match[str] | None, code_string: str
    ) -> str | None:
    """
    Given a LOINC code string and a parenthetical appositive within that
    string, this function determines whether the content within those
    parentheses constitutes an acronym for one or more preceding words
    in the code string. For example, in the phrase 

      Red Blood Cell (RBC) Count, Diff Panel

    the parenthetical 'RBC' is an acronym for 'Red Blood Cell'.

    :param parenthetical: A regex Match group representing the parenthetical
      contained within the full code string.
    :param code_string: The full text of the LOINC code string to check.
    :returns: A string comprised of the words for which the parenthetical
      is an acronym, or None if it isn't one.
    """
    if parenthetical is None:
        return None
    substring = parenthetical.group(0).replace('(', '').replace(')', '')
    paren_starts_at = parenthetical.span()[0]
    lookbacks = []
    is_first_letter = True

    # We'll go letter by letter in the parenthetical, building up a series of
    # "look-backs"--word fragments that start with a capital letter followed
    # by 0 or more lowercase letters (some acronyms have additional non-caps
    # to differentiate them, e.g. "Fr" is commonly used for "Fraction").
    for letter in substring:
        if is_first_letter:
            current_word_start = letter
            is_first_letter = False
            continue
        if letter.isupper():
            lookbacks.append(current_word_start)
            current_word_start = letter
        else:
            current_word_start += letter
    lookbacks.append(current_word_start)

    try:
        is_acronym = True
        preceding_words = code_string[:paren_starts_at].strip().split()

        # We only need to consider as many words as there are look-back checks
        acronym_candidates = preceding_words[-1 * len(lookbacks):]
        for i in range(len(lookbacks)):
            if not acronym_candidates[i].startswith(lookbacks[i]):
                is_acronym = False
                break
        if is_acronym:
            return " ".join(acronym_candidates)
    except:
        return None
    return None
    

def _substring_is_contained_in_parens(string: str, start: int, end: int) -> bool:
    """
    Determines whether the substring bounded by `start` and `end` is contained
    within a closed set of brackets or parentheses. For purposes of this function,
    start and end are assumed to work the same way sub-indexing a list or string
    does, e.g. string[start:end] would include all characters in string from 
    `start` up to _but not including_ `end`.

    :param string: The string in which the parenthetical occurs.
    :param start: The index of the first character of the substring in question.
    :param end: The index of the first character _immediately after_ the end
      of the substring (i.e. it is not part of the substring itself).
    :returns: A boolean indicating whether the substring is enclosed.
    """
    # No need to add 1 to end in this check (because during subindexing, the 
    # second value is the first thing that doesn't get used).
    if start - 1 >= 0 and end < len(string):
        if (string[start-1] == "(" and string[end] == ")") or \
            (string[start-1] == "[" and string[end] == "]"):
                return True
    return False
