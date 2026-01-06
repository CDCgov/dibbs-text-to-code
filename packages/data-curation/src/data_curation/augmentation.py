import csv
import os
import random
import re
import sys
import typing

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pydantic

from data_curation import configs
from data_curation.schemas import augmentation as schemas
from utils import normalize
from utils import path
from utils import regex_patterns

enhancements = path.load_loinc_enhancements(os.getcwd())
LOINC_ENHANCEMENTS = normalize.merge_enhancements(enhancements)
assert len(LOINC_ENHANCEMENTS) > 0

MAX_AUGMENTATION_TRIES = 100


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


def _word_deletion(
    del_count: int, words: list[str], word_details: dict, max_dels: int
) -> list[int]:
    delete_indices = []

    while len(delete_indices) < del_count:
        word_to_modify = random.randint(0, len(words) - 1)
        word_detail = word_details[word_to_modify]
        word_text = word_detail["word"]
        word_start = word_detail["start"]
        word_end = word_detail["end"]
        word_dels = word_detail["dels"]

        # ensure the word hasn't gone over the max_dels per word
        # or greater than the length of the word
        if len(word_dels) == max_dels or len(word_dels) == len(word_text):
            continue

        del_ind = -1
        # ensure that this character hasn't already been marked for delete
        while del_ind == -1:
            idx = random.randint(int(word_start), int(word_end))
            if idx not in delete_indices and idx not in word_dels:
                del_ind = idx

        delete_indices.append(idx)
        word_details[word_to_modify].get("dels").append(idx)

    return delete_indices


def _get_word_detail_by_char_range(word_details: dict, char_idx: int) -> typing.Tuple[int, dict]:
    for key, word_deets in word_details.items():
        if char_idx in range(int(word_deets["start"]), int(word_deets["end"]) + 1):
            return int(key), word_deets

    return 0, None


def _char_deletion(
    del_count: int, char_indices: list[int], word_details: dict, max_dels: int
) -> list[int]:
    delete_indices = []

    # Make sure we don't get caught looping if we physically can't
    # make as many deletion selections as there are wors/chars
    num_tries = 0
    while len(delete_indices) < del_count and num_tries < MAX_AUGMENTATION_TRIES:
        num_tries += 1
        char_to_modify = random.choice(char_indices)

        # ensure this char isn't already marked for delete
        if char_to_modify in delete_indices:
            continue

        word_idx, word_detail = _get_word_detail_by_char_range(word_details, char_to_modify)

        # make sure word details are found
        if not word_detail:
            continue

        word_text = word_detail["word"]
        word_dels = word_detail["dels"]

        # ensure the char to delete isn't in a word
        # that already has the max number of deletes
        # applied
        if len(word_dels) == max_dels or len(word_dels) == len(word_text):
            continue

        delete_indices.append(char_to_modify)
        word_details[word_idx].get("dels").append(char_to_modify)

    return delete_indices


def random_char_deletion(
    text: str,
    min_dels: int = 1,
    max_dels: int = 3,
    max_per_word: int = 2,
    method: typing.Literal["char", "word"] = "char",
) -> str:
    """
    This function randomly deletes characters from a string.  Two modes can be
    selected.
    'word' mode will randomly select words, which will then have characters
    randomly selected for deletion as long as the number of deletions per each word
    is below the max per word threshold.
    'char' mode will randomly select a series characters from the string, skipping
    any spaces, for deletion, ensuring that all words do not have more than the max
    per word deletions selected.
    The randomly select characters from both are removed from the input text and
    the result is returned.

    :param text: The input text to delete characters from.
    :param min_dels: The minimum number of characters to delete. Defaults to 1.
    :param max_dels: The maximum number of characters to delete. Defaults to 3
    :param max_per_word: The maximum number of characters to delete
        per word in the input text.  If the random number of deletes exceeds
        this input, the excess deletes will be ignored. The default is 2.
    :param method: Two methods can be chosen 'word' or 'char'.
        The default is set to 'char'
    :return: The text with characters deleted.
    """

    words = text.strip().split()
    char_indices = [i for i, char in enumerate(text) if char not in (" ")]
    words_details = {}
    delete_indices = []

    # get indexes of start and end of each word
    # within given string and store them in dict
    # for use later. Ensures randomness in word selection
    # even with repeating words in the string
    starting_char = 0
    for i, word in enumerate(words):
        for m in re.finditer(re.escape(word), text):
            indexes = {
                "word": m.group(),
                "start": m.start(),
                "end": m.end() - 1,
                "dels": [],
            }
            # ensure only the next first instance of the word is
            # used to create the next word detail record
            if m.start() >= starting_char and not words_details.get(i):
                words_details[i] = indexes
                starting_char = m.end()

    # get random number of deletes within specified range
    deletion_count = min(random.randint(min_dels, max_dels), (len(words) - 1) * max_per_word)

    # ensure the deletion count is not bigger than all the word characters
    if deletion_count > len(char_indices):
        deletion_count = len(char_indices - 1)

    # word method
    if method == "word":
        delete_indices = _word_deletion(deletion_count, words, words_details, max_per_word)

    # char method
    elif method == "char":
        delete_indices = _char_deletion(deletion_count, char_indices, words_details, max_per_word)

    # reconstruct the string by reconstructing the chars that aren't delete indices
    result_chars = [char for i, char in enumerate(text) if i not in delete_indices]
    return "".join(result_chars)


def insert_loinc_related_names(
    text: str, loinc_names: list[str], max_inserts: int, min_inserts: int = 1
) -> str:
    """
    Inserts 1 or more LOINC related names into the input text at random positions.

    :param text: The input text to modify.
    :param loinc_names: A list of LOINC related names to insert.
    :param num_inserts: The number of LOINC names to insert.
    :return: The text with LOINC related name(s) inserted.
    """
    words = text.split()
    if not loinc_names or len(words) < 1:
        return text

    # Ensure num_inserts does not exceed the number of loinc_names
    num_inserts = random.randint(min_inserts, min(len(loinc_names), max_inserts))

    # Select indices to insert at (can repeat)
    indices_to_insert = [random.randrange(len(words) + 1) for _ in range(num_inserts)]

    # Select unique LOINC names to insert
    loinc_names_to_insert = random.sample(loinc_names, num_inserts)

    for _ in range(num_inserts):
        name_to_insert = loinc_names_to_insert.pop()
        idx_to_insert = indices_to_insert.pop()
        words.insert(idx_to_insert, name_to_insert.strip())

    return " ".join(words)


@pydantic.validate_call
def enhance_loinc_str(
    text: str,
    enhancement_type: schemas.EnhancementType,
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
    if max_enhancements <= min_enhancements:
        raise ValueError("max_enhancements must be greater than min_enhancements")

    # Step 1: build all substring candidates, including singletons
    words = [(word.strip(), [i]) for i, word in enumerate(text.split())]
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
    words: list[str, list[int]],
    disjoint_candidates: list[typing.Tuple[str, typing.Tuple[int, int]]],
    enhancement_type: typing.Annotated[schemas.EnhancementType, pydantic.Field()],
    num_enhancements: int,
) -> list[str, list[int]]:
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
    enhancements_to_apply: list[typing.Tuple[list[int], str]] = []
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
    candidates: list[typing.Tuple[str, typing.Tuple[int, int]]],
) -> list[typing.Tuple[str, list[int]]]:
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
    candidates: list[typing.Tuple[str, typing.Tuple[int, int]]],
    loinc_enhancements: dict,
) -> list[str, list[int]]:
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
    words: list[typing.Tuple[str, list[int]]],
) -> list[typing.Tuple[str, typing.Tuple[int, int]]]:
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
    for word, [position] in words:
        candidates.append((word, (position, position)))

    # Now build up all sequentially linear combinations of substrings
    for start_idx in range(len(words)):
        for end_idx in range(start_idx + 2, len(words) + 1):  # ensures at least 2 words
            substring = " ".join(word for word, _ in words[start_idx:end_idx])
            # Need the -1 to map back into the same space as our singletons, because
            # the endpoint is now inclusive
            candidates.append((substring, (start_idx, end_idx - 1)))

    return candidates


def generate_augmented_examples(
    input_code: str,
    related_names: list[str],
    num_examples: int,
    config: schemas.AugmentationConfig,
):
    """
    Given a LOINC code string, generates a specified number of augmented
    training examples, which are returned as a list. Each augmented example is
    probabilistically operated on by a scrambling or enhancement function
    above to create a semantically and syntactically variant instance. The
    order of augmentation operations is always enhancement, insertion,
    permutation, then deletion.

    :param input_code: The LOINC code string to generate augmented copies of.
    :param related_names: A list of strings consisting of the LOINC "Related
      Names" field pulled from the SNOINC extracts.
    :param num_examples: The number of augmented examples to generate.
    :param config: An Augmentation Configuration object indicating the
      thresholds, options, and probabilities used to modify the example.
    :returns: A list of augmented training examples.
    """

    augmented_examples = []
    for _ in range(num_examples):
        ex_code = input_code
        performed_enhancement = False

        if "enhancement_all" in config:
            prob = random.uniform(0.0, 1.0)
            if prob <= config["enhancement_all"]["enhancement_prob"]:
                performed_enhancement = True
                ex_code = enhance_loinc_str(
                    text=input_code,
                    enhancement_type="all",
                    max_enhancements=config["enhancement_all"]["max_enhances"],
                )
        else:
            if "enhancement_synonyms" in config:
                prob = random.uniform(0.0, 1.0)
                if prob <= config["enhancement_synonyms"]["enhancement_prob"]:
                    performed_enhancement = True
                    ex_code = enhance_loinc_str(
                        text=input_code,
                        enhancement_type="synonyms",
                        max_enhancements=config["enhancement_synonyms"]["max_enhancements"],
                    )
            if "enhancement_abbreviation" in config:
                prob = random.uniform(0.0, 1.0)
                if prob <= config["enhancement_abbreviation"]["enhancement_prob"]:
                    performed_enhancement = True
                    ex_code = enhance_loinc_str(
                        text=input_code,
                        enhancement_type="abbrv",
                        max_enhancements=config["enhancement_abbreviation"]["max_enhancements"],
                    )

        # Use the right insertion probability threshold
        # Inserts come after enhancements so that the random index any related
        # names are inserted at doesn't interfere with substring searching
        # for acronyms or abbreviations
        if performed_enhancement:
            t = config["insertion"]["insert_prob_after_enhance"]
        else:
            t = config["insertion"]["insert_prob_without_enhance"]
        prob = random.uniform(0.0, 1.0)
        if prob <= t:
            ex_code = insert_loinc_related_names(
                ex_code,
                related_names,
                config["insertion"]["max_inserts"],
                config["insertion"]["min_inserts"],
            )

        # Next comes permutations, if applicable; no risk of interference
        # with deletions, but they have to come after enhancements for the
        # same reasons as insertions, and insertions have priority as the
        # only other mechanism to insert new semantic meaning
        prob = random.uniform(0.0, 1.0)
        if prob <= config["permutation"]["swap_prob"]:
            ex_code = scramble_word_order(
                ex_code, config["permutation"]["max_swaps"], config["permutation"]["min_swaps"]
            )

        # Last come the deletions: must be the final operation because
        # they're syntactically destructive, and other operations depend on
        # the full syntax of each token
        prob = random.uniform(0.0, 1.0)
        if prob <= config["deletion"]["deletion_prob"]:
            ex_code = random_char_deletion(
                ex_code,
                config["deletion"]["min_deletes"],
                config["deletion"]["max_deletes"],
                config["deletion"]["max_deletes_per_word"],
                config["deletion"]["deletion_mode"],
            )

        ex_code = re.sub(regex_patterns.MULTIPLE_SPACE, " ", ex_code)
        augmented_examples.append(ex_code.strip())

    return augmented_examples


def build_augmented_loinc_files(
    input_path: str,
    config: schemas.LoincFileGenerationConfig,
    num_lcn: int = 5,
    num_sn: int = 5,
    num_dn: int = 5,
    output_path_base: str = "../data/training_files/augmented_loinc",
) -> None:
    """
    Generates augmented LOINC data files for the long common names, short
    common names, and display names based on the provided configurations.

    :param input_path: The path to the base LOINC name file.
    :param configs: Configuration dictionaries for long common names, short
        common names, and display names.
    :param num_lcn: The number of augmented long common names to generate.
    :param num_sn: The number of augmented short common names to generate.
    :param num_dn: The number of augmented display names to generate.
    :param output_files_base: The base path for the output files.
    :return: None
    """

    num_map = {"short_name": num_sn, "long_common_name": num_lcn, "display_name": num_dn}

    # Read in data/loinc_lab_names_XXXX.csv
    with open(
        input_path,
        encoding="utf-8",
    ) as fp:
        data = fp.readlines()

    # First row of the data is a header
    data = data[1:]

    for row in data:
        r = row.split("|")
        # skip any malformed rows
        if len(r) < 6:
            continue

        loinc_code, short_name, long_name, display_name = r[0], r[1], r[2], r[3]
        related_names = r[5].split(";") if r[5] else []
        values = {
            "short_name": re.sub(regex_patterns.MULTIPLE_SPACE, " ", short_name),
            "long_common_name": re.sub(regex_patterns.MULTIPLE_SPACE, " ", long_name),
            "display_name": re.sub(regex_patterns.MULTIPLE_SPACE, " ", display_name),
        }

        for key, base_value in values.items():
            if base_value != "":
                augmented_examples = generate_augmented_examples(
                    base_value, related_names, num_map[key], config[key]
                )

                # Append data to respective files
                # Note: these files should be opened using a CSV reader
                with open(f"{output_path_base}_{key}.csv", "a", encoding="utf-8", newline="") as fp:
                    writer = csv.writer(fp, delimiter=":")  # use ":" instead of default ","
                    writer.writerow([loinc_code, base_value, "|".join(augmented_examples)])


if __name__ == "__main__":
    build_augmented_loinc_files(
        "../data/snoinc_extracts/loinc_lab_names_20251008.csv",
        configs.LOINC_FILE_GENERATION_AUGMENTATION,
        num_lcn=1,
        num_sn=1,
        num_dn=1,
        output_path_base="../data/augmented_",
    )
