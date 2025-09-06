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
    This function randomly deletes characters from a string.  One can specify the
    maximum number of deletions per word.
    """

    if min_deletions <= 0 or max_deletions <= 0 or method not in DELETE_METHODS:
        # TODO: log some info here?
        return text

    deletion_count = random.randint(min_deletions, max_deletions)
    print(f"DCOUNT: {deletion_count}")

    words = text.split()
    words_details = {}
    delete_indices = []
    for i, word in enumerate(words):
        for m in re.finditer(word, text):
            indexes = {"word": m.group(), "start": m.start(), "end": m.end() - 1}
            words_details[i] = indexes

    if method == "word":
        print(f"LW: {len(words)}")
        word_to_modify = random.randint(0, len(words) - 1)
        print(f"WM: {word_to_modify}")
        word_detail = words_details[word_to_modify]
        delete_indices = get_delete_indices(word_detail, deletion_count, max_deletions_per_word)

    elif method == "char":
        total_deletes = deletion_count
        words_modified = []

        while total_deletes > 0:
            if len(words_modified) == len(words) or len(delete_indices) == deletion_count:
                break
            print(f"Total DELS: {total_deletes}")
            word_delete_count = random.randint(1, total_deletes)
            print(f"WORD DEL: {word_delete_count}")
            word_to_modify = random.randint(0, len(words) - 1)
            while word_to_modify in words_modified:
                word_to_modify = random.randint(0, len(words) - 1)
            words_modified.append(word_to_modify)
            word_detail = words_details[word_to_modify]
            delete_indices.extend(get_delete_indices(word_detail, word_delete_count, max_deletions))
            total_deletes = total_deletes - word_delete_count
            # print(f"WORDS MOD LIST: {words_modified}")

    print(f"DEL INDS: {delete_indices}")
    result_chars = [char for i, char in enumerate(text) if i not in delete_indices]
    return "".join(result_chars)


def get_delete_indices(word_details: dict, delete_count: int, max_deletes: int) -> list[int]:
    """
    Gets the indexes of the characters that are to be deleted with some rules
    """
    actual_word = word_details.get("word")

    if max_deletes > 0 and delete_count > max_deletes:
        sample_count = max_deletes
    else:
        sample_count = delete_count

    if sample_count > len(actual_word):
        sample_count = len(actual_word)

    word_start = word_details.get("start")
    word_end = word_details.get("end")
    print(f"WORD: {actual_word}, START: {word_start}, END: {word_end}")

    delete_indices = []
    # loop through this for delete count
    for i in (1, sample_count):
        delete_index = random.randint(word_start, word_end)
        print(f"DEL INDEXA: {delete_index}")
        while delete_index in delete_indices:
            delete_index = random.randint(word_start, word_end)
        print(f"DEL INDEXB: {delete_index}")
        delete_indices.append(delete_index)

    return delete_indices
