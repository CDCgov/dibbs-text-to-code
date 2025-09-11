import random
import re
import typing
from typing import Tuple


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


def _get_word_detail_by_char_range(word_details: dict, char_idx: int) -> Tuple[int, dict]:
    for key, word_deets in word_details.items():
        if char_idx in range(int(word_deets["start"]), int(word_deets["end"])):
            return int(key), word_deets

    return 0, None


def _char_deletion(
    del_count: int, char_indices: list[int], word_details: dict, max_dels: int
) -> list[int]:
    delete_indices = []

    while len(delete_indices) < del_count:
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
    deletion_count = min(random.randint(min_dels, max_dels), len(words) - 1)

    # ensure the deletion count is not bigger than all the word characters
    if deletion_count > len(char_indices):
        deletion_count = len(char_indices - 1)

    ####### word method ######
    if method == "word":
        delete_indices = _word_deletion(deletion_count, words, words_details, max_per_word)

    ####### char method ######
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
        words.insert(idx_to_insert, name_to_insert)

    return " ".join(words)
