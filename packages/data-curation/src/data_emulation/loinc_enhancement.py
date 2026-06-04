import os
import random
import re
import sys
from typing import Sequence, Tuple

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pydantic

from data_emulation.schemas import enhancement_type as schemas
from utils import normalize
from utils import path
from utils import regex_patterns

enhancements = path.load_loinc_enhancements(os.getcwd())
LOINC_ENHANCEMENTS = normalize.merge_enhancements(enhancements)
assert len(LOINC_ENHANCEMENTS) > 0

MAX_AUGMENTATION_TRIES = 100

TokenSpan = Tuple[int, int]
EnhancementCandidate = Tuple[str, TokenSpan]

@pydantic.validate_call
def enhance_loinc_str(
    text: str,
    enhancement_type: schemas.EnhancementType | str,
    max_enhancements: int,
    min_enhancements: int = 1,
) -> str:
    """
    Enhances the input text by applying specified enhancement techniques.
    :param text: The input text to enhance.
    :param enhancement_type: The type of enhancement to apply. Options are:
        - "abbrv": Replace words with their abbrveviations.
        - "synonyms": Replace words with semantically related terms.
        - "all": Apply all of the above techniques.
    :param max_enhancements: The maximum number of enhancements to apply.
    :param min_enhancements: The minimum number of enhancements to apply.
    :return: The enhanced text.
    """
    if max_enhancements < min_enhancements:
        raise ValueError("max_enhancements must be greater than min_enhancements")

    # Step 1: build all substring candidates, including singletons
    words = [(word.strip(), (i, i)) for i, word in enumerate(text.split())]
    candidates = _generate_enhancement_candidates(words)

    # Step 2: check each one for eligibility for a LOINC enhancement and
    # filter to only those that have one
    enhancemenet_eligible_strings = _filter_candidates_for_enhancement(
        candidates, LOINC_ENHANCEMENTS
    )

    if len(enhancemenet_eligible_strings) < 1:
        # We found no options in the LOINC dictionary at all, nothing more
        # to do
        return text

    # Step 3: construct the maximally disjoint interval list.
    # Because we've iteratively constructed substrings, it's possible that
    # some short substrings (e.g. indices [3,7]) are contained within longer
    # substrings ([3,9]). It's further possible that the set difference
    # in containment is not itself a susbtring with a valid LOINC enhancement
    # ([8,9] in this case wouldn't occur). We thus need the maximum number of
    # non-intersecting, fully disjoint index sets.
    maximal_candidate_set = _generate_disjoint_intervals(enhancemenet_eligible_strings)

    # Step 4: determine number of enhancements we can actually perform
    if len(maximal_candidate_set) < min_enhancements:
        num_enhancements = len(maximal_candidate_set)
    else:
        num_enhancements = random.randint(
            min_enhancements, min(max_enhancements, len(maximal_candidate_set))
        )

    # Step 5: Actually perform enhancement and return
    words = _apply_enhancements(words, maximal_candidate_set, enhancement_type, num_enhancements)
    reconstructed_text = re.sub(regex_patterns.MULTIPLE_SPACE, " ", " ".join(w[0] for w in words))
    return reconstructed_text.strip()


def _apply_enhancements(
    words: list[EnhancementCandidate],
    disjoint_candidates: list[EnhancementCandidate],
    enhancement_type: schemas.EnhancementType | str,
    num_enhancements: int,
) -> list[EnhancementCandidate]:
    """
    Apply LOINC enhancement to a provided tokenized copy of a code string. The
    code string and a list of possible candidates that are eligible to be
    enhanced are used to randomly sample some strings for replacement, and
    then the original string is modified in reverse to leverage index-based
    token intervals.

    :param words: The list of words in the input text with their indices.
    :param disjoint_candidates: A list of substrings that have LOINC enhancements
      available and that do not overlap one another.
    :param enhancement_type: The type of enhancement to apply.
    :param num_enhancements: The number of enhancements to apply.
    :return: The modified list of words and indices.
    """
    enhancements_applied = 0
    enhancements_used = set()
    num_tries = 0

    # We'll need to generate all enhancements before applying any and then
    # work backwards by string index; otherwise, we could change single words
    # into multiples early in the string and ruin the indices of all words
    # that come later
    enhancements_to_apply: list[Tuple[Tuple[int, int], str]] = []
    while enhancements_applied < num_enhancements and num_tries < MAX_AUGMENTATION_TRIES:
        num_tries += 1

        # If we need to change type based on synonym/abbreviation availability,
        # make sure that switch only affects the current enhancement; we'll try
        # the full suite on the next enhancement because it might be available
        e_type_to_use = enhancement_type

        selection = random.choice(disjoint_candidates)
        if selection in enhancements_used:
            continue
        word_to_enhance = selection[0]
        enhancement_idx = selection[1]
        enhancements_used.add(selection)

        possible_enhancements = LOINC_ENHANCEMENTS[word_to_enhance.lower()]

        if not possible_enhancements.get(e_type_to_use) and e_type_to_use != "all":
            continue

        if e_type_to_use == "all":
            # Randomly choose between abbrveviation and synonyms, then
            # randomly pick an enhancement from the available options
            e_type_to_use = random.choice(["abbrv", "synonyms"])
            # If there are no enhancements of the chosen type, switch to the other type
            if not possible_enhancements.get(e_type_to_use):
                e_type_to_use = "abbrv" if e_type_to_use == "synonyms" else "synonyms"

        enhancement = random.choice(possible_enhancements[e_type_to_use])
        enhancement = re.sub(regex_patterns.MULTIPLE_SPACE, " ", enhancement)
        enhancements_applied += 1
        enhancements_to_apply.append((enhancement_idx, enhancement.strip()))

    # Sort by substring start index, since we know everything is disjoint.
    # This lets us completely replace one string before hitting another.
    enhancements_to_apply = sorted(enhancements_to_apply, key=lambda x: x[0][0], reverse=True)
    for (start, end), replacement in enhancements_to_apply:
        # Base case: singletons are easy to replace
        if start == end:
            words[start] = (replacement, (start, end))
        # Substring case involves replacing out a list of tokens, so we
        # can just slice it out and overwrite all at once
        else:
            words[start : end + 1] = [(replacement, (start, end))]

    return words


def _generate_disjoint_intervals(
    candidates: list[EnhancementCandidate],
) -> list[EnhancementCandidate]:
    """
    Given a list of tuples that include string index intervals, construct the
    largest possible list of those intervals such that no interval intersects
    with or overlaps another. This allows us to combine both singleton tokens
    and substrings in the same enhancement search, so that we can perform both
    on a single string if there are enough candidates.

    :param candidates: A list of tuples of strings and the start:end indices at
      which they occur.
    :returns: A list containing the largest set of the original tuples whose
      occurrence intervals do not overlap.
    """

    # We start by sorting the candidates according to their interval's
    # *end* index--we can build the maximally disjoint set in a single
    # pass by adding as many intervals as possible before the next
    # ending index
    candidates = sorted(candidates, key=lambda x: x[1][1])

    result = []
    current_end = -1

    for replacement, (start, end) in candidates:
        # Next interval starts after our current one ends
        if start > current_end:
            result.append((replacement, (start, end)))
            current_end = end

    return result


def _filter_candidates_for_enhancement(
    candidates: list[EnhancementCandidate],
    loinc_enhancements: dict,
) -> list[EnhancementCandidate]:
    """
    Given a list of candidate words and substrings, filter the list to only contain
    tuples for which the candidate has one or more enhancements available in the
    LOINC_ENHANCEMENTS dictionary.

    :param candidates: A list of tuples of words and their inclusive indices. Each
      such candidate will be checked independently for an eligible enhancement.
    :param loinc_enhancements: A dictionary containing eligible enhancements
      that can be made on a substring in the input code.
    :return: A filtered list containing only tuples for which an eligible
      enhancement was found.
    """
    filtered_candidates = []

    for word, idx in candidates:
        # Applying the lowercasing here lets us still reconstruct the string with
        # other capitalization preserved
        search_word = word.lower()
        if word.lower() in loinc_enhancements:
            # Only add if there are enhancements available
            if not loinc_enhancements[search_word].get("abbrv") and not loinc_enhancements[
                search_word
            ].get("synonyms"):
                continue
            filtered_candidates.append((word, idx))

    return filtered_candidates


def _generate_enhancement_candidates(
    words: Sequence[EnhancementCandidate],
) -> list[EnhancementCandidate]:
    """
    From a tokenized string, generate a list of all possible candidate strings and
    substrings that might have LOINC enhancements available to them. A substring
    will be included in the final list if either: a) it is constructed of a single
    word (represented by an interval whose start and end indices are the same, e.g.
    [2,2]), or b) it is composed of 2 or more words.

    :param words: List of words, including their indices, from which to generate
      candidates.
    :return: List of all candidate singletons and substrings, including indices.
    """
    # Start with all singletons, and make their token range denote
    # a point rather than an interval (will need this later for maximally
    # disjoint interval computation)
    candidates = []
    for word, positions in words:
        position = positions[0]
        candidates.append((word, (position, position)))

    # Now build up all sequentially linear combinations of substrings
    for start_idx in range(len(words)):
        for end_idx in range(start_idx + 2, len(words) + 1):  # ensures at least 2 words
            substring = " ".join(word for word, _ in words[start_idx:end_idx])
            # Need the -1 to map back into the same space as our singletons, because
            # the endpoint is now inclusive
            candidates.append((substring, (start_idx, end_idx - 1)))

    return candidates
