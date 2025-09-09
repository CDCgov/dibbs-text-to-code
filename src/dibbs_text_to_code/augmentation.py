import random
import re

DELETE_METHODS = ["char", "word"]


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


def random_char_deletion(
    text: str,
    min_deletions: int,
    max_deletions: int,
    max_deletions_per_word: int = 0,
    method: str = "char",
) -> str:
    """
    This function randomly deletes characters from a string.  Two modes can be
    selected.  'word' mode will randomly select a word from the string
    and delete a random number of characters, lower than the max_deletions_per_word
    specified.  'char' mode will randomly select a series of words from the string
    and delete a random number of characters from that word, below the specified
    max_deletions_per_word.

    :param text: The input text to delete characters from.
    :param min_deletions: The minimum number of characters to delete.
    :param max_deletions: The maximum number of characters to delete.
    :param max_deletions_per_word: The maximum number of characters to delete
        per word in the input text.  If the random number of deletes exceeds
        this input, the excess deletes will be ignored. The default is 0.
    :param method: Two methods can be chosen.
        word - delete random characters from a random word in the input text.
        char - delete random characters from randomly selected words in the
            input text.
        The default is set to 'char'
    :return: The text with words scrambled.
    """

    # if incorrect deletion number range passed in
    # or incorrect mode selected
    # return the original string
    if (
        min_deletions < 0
        or min_deletions > max_deletions
        or max_deletions <= 0
        or method not in DELETE_METHODS
    ):
        # TODO: log some info here?
        return text

    # get random number of deletes within specified range
    deletion_count = random.randint(min_deletions, max_deletions)

    words = text.split()
    words_details = {}
    delete_indices = []

    # print(f"WORDS: {words}")
    # get indexes of start and end of each word
    # within given string and store them in dict
    # for use later. Ensures randomness in word selection
    # even with repeating words in the string
    starting_char = 0
    for i, word in enumerate(words):
        # print(f"WI: {i}")
        for m in re.finditer(re.escape(word), text):
            indexes = {"word": m.group(), "start": m.start(), "end": m.end() - 1}
            # print(f"    WORD DEET: {indexes}")
            # ensure only the next first instance of the word is
            # used to create the next word detail record
            if m.start() >= starting_char and not words_details.get(i):
                words_details[i] = indexes
                # print(f"        FOUND: {indexes}")
                starting_char = m.end()

    # print(f"ALL WORDS DEETS: {words_details}")
    # word method
    # take random word and find random delete indices
    # for chars in the word under the max number of deletes per word
    if method == "word":
        word_to_modify = random.randint(0, len(words) - 1)
        word_detail = words_details[word_to_modify]
        delete_indices = _get_delete_indices(word_detail, deletion_count, max_deletions_per_word)

    # char method
    # select multiple random words and randomly get char indices for delete
    # for each word until delete count is reached, making sure each word
    # doesn't have more deletes in it above the max number of deletes per word.
    # Each word in the string will only be modified once.
    elif method == "char":
        total_deletes = deletion_count
        words_modified = []

        # loop through delete count
        while total_deletes > 0:
            # print(f"TOTAL DELS (in loop): {total_deletes}")
            # print(f"DEL COUNT (in loop): {deletion_count}")
            # print(f"DEL IND ARRAY (in loop): {len(delete_indices)}")

            # exit loop if every word in string has already been modified
            # or if the number of deletes have been met
            if len(words_modified) == len(words) or len(delete_indices) == deletion_count:
                break

            # get just a portion of the deletes to handle for this word
            word_delete_count = random.randint(1, total_deletes)

            # print(f"WORD DEL COUNT: {word_delete_count}")

            # select a word from the string randomly
            word_to_modify = random.randint(0, len(words) - 1)
            # print(f"WM (in loop): {word_to_modify}")

            # ensure the word hasn't already been modified
            while word_to_modify in words_modified:
                word_to_modify = random.randint(0, len(words) - 1)
            words_modified.append(word_to_modify)
            # print(f"WM LIST (in loop): {words_modified}")

            word_detail = words_details[word_to_modify]
            delete_indices.extend(
                _get_delete_indices(word_detail, word_delete_count, max_deletions_per_word)
            )
            total_deletes = total_deletes - word_delete_count

    # perform the deletes of the randomly selected chars in the string and return it
    result_chars = [char for i, char in enumerate(text) if i not in delete_indices]
    return "".join(result_chars)


def _get_delete_indices(word_details: dict, delete_count: int, max_deletes: int) -> list[int]:
    """
    Gets the indexes of the characters, of a word from the input text,
    that are to be deleted.  This functin also applies the various rules
    related to maximum deletes per word.
    """
    actual_word = word_details.get("word")
    if not actual_word:
        return []

    # print(f"ACTUAL WORD: {actual_word}")
    # print(f"WORD DEETS: {word_details}")
    # ensure the number of deletes for this word
    # does not exceed max deletes per word.
    # If it does just use the max delete per word
    # as the ceiling of deletes.
    print(f"DEL COUNT (BEFORE): {delete_count}")
    print(f"DEL MAX: {max_deletes}")

    if max_deletes > 0 and delete_count > max_deletes:
        sample_count = max_deletes
    else:
        sample_count = delete_count
    print(f"DEL COUNT (after): {sample_count}")

    # if number of deletes exceeds the length of
    # the word selected, just delete the whole word
    # TODO: Should we limit this or will this work?
    if sample_count > len(actual_word):
        sample_count = len(actual_word)
    print(f"DEL COUNT (after2): {sample_count}")

    # get indices of word within input text
    # ensures if repeating words in text that
    # the correct word is modified.
    word_start = word_details.get("start")
    word_end = word_details.get("end")

    delete_indices = []
    # Keep getting random characters from word
    # to delete until number of deletes (sample_count) is reached
    while len(delete_indices) < sample_count:
        delete_index = random.randint(word_start, word_end)
        # print(f"DEL IND (Initial): {delete_index}")
        my_count = 0
        # ensure that index hasn't already been selected for delete
        while delete_index in delete_indices:
            # print(f"DEL IND (LOOP) {my_count}: {delete_index}")
            delete_index = random.randint(word_start, word_end)
            my_count = my_count + 1
        delete_indices.append(delete_index)

        # print(f"IND LIST: {delete_indices}")
    # print(f"FINAL IND LIST: {delete_indices}")

    return delete_indices


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
