#!/usr/bin/env python3

"""
Generate a CSV of synthetic lab results with labeled values.

Each row contains a randomized result word (e.g., "positive", "not detected")
and a label: 1 for positive terms, 2 for negative terms. Optionally, the
script can introduce randomized case changes and typos.

Usage:
    ./synthetic_lab_results.py <number_of_rows>
    ./synthetic_lab_results.py 1000 --change-case 0.5 --introduce-typo 0.1

To view all options and usage details:
    ./synthetic_lab_results.py --help
"""

import argparse
import csv
import random
import sys

positive_words = [
    "positive",
    "detected",
    "reactive",
    "present",
    "abnormal",
    "elevated",
    "high",
    "found",
    "1+",
    "true",
    "confirmed",
]
negative_words = [
    "negative",
    "not detected",
    "non-reactive",
    "absent",
    "normal",
    "undetected",
    "clear",
    "false",
    "0",
    "no value",
]


def random_case(word):
    """
    Randomly change the case of a word.
    """
    choice = random.choice(["upper", "lower", "capitalize", "none"])
    if choice == "upper":
        return word.upper()
    elif choice == "lower":
        return word.lower()
    elif choice == "capitalize":
        return word.capitalize()
    return word


def introduce_typo(word):
    """
    Introduce a typo in a word.
    """
    if len(word) < 2:
        return word
    typo_type = random.choice(["sub", "del", "ins"])
    idx = random.randint(0, len(word) - 1)
    c = random.choice("abcdefghijklmnopqrstuvwxyz")
    if typo_type == "sub":
        return word[:idx] + c + word[idx + 1 :]
    elif typo_type == "del":
        return word[:idx] + word[idx + 1 :]
    elif typo_type == "ins":
        return word[:idx] + c + word[idx:]
    return word


def probability_float(x):
    """
    Validate a probability float.
    """
    try:
        x = float(x)
    except ValueError:
        raise argparse.ArgumentTypeError(f"'{x}' not a floating-point literal")
    if x < 0.0 or x > 1.0:
        raise argparse.ArgumentTypeError(f"'{x}' not in range [0.0, 1.0]")
    return x


def main():
    """
    Generate synthetic lab result words.
    """
    parser = argparse.ArgumentParser(
        description="Generate synthetic lab result words with labels (1=positive, 2=negative)."
    )
    parser.add_argument("num_rows", type=int, help="Number of rows to generate")
    parser.add_argument(
        "--output",
        type=argparse.FileType("w"),
        default=sys.stdout,
        help="File to write output to (default: STDOUT)",
    )
    parser.add_argument(
        "--change-case",
        type=probability_float,
        default=0.5,
        help="Probability of changing case (default: 0.5)",
    )
    parser.add_argument(
        "--introduce-typo",
        type=probability_float,
        default=0.1,
        help="Probability of introducing a typo (default: 0.1)",
    )
    args = parser.parse_args()

    count = args.num_rows
    writer = csv.writer(args.output)
    writer.writerow(["word", "label"])

    all_words = [(w, 1) for w in positive_words] + [(w, 2) for w in negative_words]

    for _ in range(count):
        word, label = random.choice(all_words)
        if random.random() < args.change_case:
            word = random_case(word)
        if random.random() < args.introduce_typo:
            word = introduce_typo(word)
        writer.writerow([word, label])


if __name__ == "__main__":
    main()
