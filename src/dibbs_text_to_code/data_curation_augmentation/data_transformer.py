#!/usr/bin/env python

import random
import re

DELETE_METHODS = ["char", "word"]
NON_WORD_CHARS = [":", ",", ";", "-", "]", "[", "'"]
WORD_SEPARATORS = [":", ",", ";"]

"""
The function should take as parameters min_deletions and max_deletions, integers specifying the minimum and maximum 
number of deletions to perform in the overall string. The number of deletions the function actually does should be randomly generated.

The function should also take a parameter max_deletes_per_word, which is the maximum number of times a given word in the string 
can have one of its characters chosen for a deletion. If the number of deletions chosen exceeds 
num_words * max_deletes_per_word, excess deletions should be skipped.

The method of choosing which character to delete should be configurable as an input parameter, 
‘character’ or ‘word’: if character, then the choice is randomized over all characters in the 
string, if word, then a word is first randomly chosen and then a character in the word is chosen
The function should return a new code string with deletions applied.

Should have unit tests.
"""


# separated this out into it's own function for
# potential use later in other functions as
# well as to be able to test it separately
def get_words(text: str) -> list[str]:
    """
    Gets the word count of the passed in string.
    """
    if not text:
        return 0

    pattern = r"\b[WORD_SEPARATORS]*[a-zA-Z0-9\-\'\(\)\+]+[WORD_SEPARATORS]*\b"
    # print(f"WORDS: {re.findall(pattern, text)}")
    return re.findall(pattern, text)


# separated this out into it's own function for
# potential use later in other functions as
# well as to be able to test it separately
def get_char_count(text: str) -> int:
    """
    Gets the character count of the passed in string.
    """
    if not text:
        return 0
    char_count = len(text)
    char_count = char_count - text.count(" ")
    char_count = char_count - text.count(",")
    return char_count


def random_char_word_deletion(
    text_to_modify: str,
    min_deletions: int,
    max_deletions: int,
    max_deletions_per_word: int = 0,
    method: str = "char",
) -> str:
    """
    This function randomly deletes characters from a string.  One can specify the
    maximum number of deletions per word.
    """
    modified_text = text_to_modify
    deletion_count = random.randint(min_deletions, max_deletions)

    if min_deletions <= 0 or max_deletions <= 0 or method not in DELETE_METHODS:
        # TODO: log some info here?
        return text_to_modify

    char_count = get_char_count(text_to_modify)
    if deletion_count > char_count:
        deletion_count = char_count / 10
    words_from_text = get_words(text_to_modify)
    word_count = len(words_from_text)
    print(f"COUNTS: CHAR: {char_count} WORD: {word_count}")

    # If the number of deletions chosen exceeds num_words * max_deletes_per_word, excess deletions should be skipped.
    if max_deletions_per_word > 0 and (deletion_count > (max_deletions_per_word * word_count)):
        deletion_count = max_deletions_per_word * word_count

    return modified_text
