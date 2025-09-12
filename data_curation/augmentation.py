import random
import typing


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


def enhance_loinc_str(
    text: str,
    enhancement_type: typing.Literal["abbreviation", "acryonym", "replacement", "all"],
    enhancements: typing.Dict,
    max_enhancements: int,
    min_enhancements: int = 1,
) -> str:
    """
    Enhances the input text by applying specified enhancement techniques.
    :param text: The input text to enhance.
    :param enhancement_type: The type of enhancement to apply. Options are:
        - "abbreviation": Replace words with their abbreviations.
        - "acronym": Replace phrases with their acronyms.
        - "replacement": Replace words with semantically related terms.
        - "all": Apply all of the above techniques.
    :param max_enhancements: The maximum number of enhancements to apply.
    :param min_enhancements: The minimum number of enhancements to apply.
    :return: The enhanced text.
    """
    words = text.split()
    print(words)

    # Check that there are words to enhance
    applicable_enhancements = enhancements.get(enhancements.key)
    if not applicable_enhancements:
        return text

    # Choose number of enhancements to apply
    num_enhancements = random.randint(min_enhancements, max_enhancements)
    print(f"Applying {num_enhancements} enhancements of type {enhancement_type}")

    return text
