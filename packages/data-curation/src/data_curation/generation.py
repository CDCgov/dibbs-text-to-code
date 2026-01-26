import csv
import random

BASE_FILE_PATH = "../../../../data/training_files/fine_tuning"
OUT_FILE_PATH = "../../../../data/training_files/fine_tuning_positive_pairs.txt"


def generate_positive_pairs(file_handle: str, num_examples: int, out_file: str):
    """
    Given the location of one or more files of LOINC codes and some corresponding
    augmented examples for those codes, this function compiles a list of
    positive pairs that can be read for model training. A positive pair is a
    tuple of the form (original_loinc_code, augmented_example_of_code).

    :param file_handle: Either the path to a specific file of LOINC codes and
      examples, or the prefix path for multiple data files across name variants.
    :param num_examples: The number of positive pairs to generate. If -1, one
      positive pair will be created for every element in the pool spanned by
      the files accessible via the handle parameter.
    :param out_file: The destination at which to write the positive pair file.
    :returns: None
    """

    handle_parts = file_handle.split(".")
    data_pool = []
    pairs = []

    # Given handle is a prefix to multiple files, so we'll use naming
    # conventions to open the three appropriate ones
    if len(handle_parts) == 0 or handle_parts[-1] != "txt":
        for variant in ["long_common_name.csv", "short_name.csv", "display_name.csv"]:
            with open(file_handle + "_" + variant, "r") as csvfp:
                rows = csv.reader(csvfp, delimiter=":")
                _append_to_data_pool(rows, data_pool)

    # Handle is actually a file, can just open that
    else:
        with open(file_handle, "r") as csvfp:
            rows = csv.reader(csvfp, delimiter=":")
            _append_to_data_pool(rows, data_pool)

    # Pre-specified number of examples to generate
    # If num_examples is -1, that's "generate all" mode, where we
    # produce one positive pair per code in the data pool, but we
    # can achieve that just by not truncating the pool list
    if num_examples != -1:
        random.shuffle(data_pool)
        data_pool = data_pool[:num_examples]

    for element in data_pool:
        base_code = element[1].strip()
        augmented_examples = element[2].strip().split("|")

        # Randomly choose one of the augmented examples to pair
        chosen_ex = random.choice(augmented_examples)
        pairs.append((base_code, chosen_ex.strip()))

    # Now we just write the created examples to the output file
    with open(out_file, "w") as fp:
        for pair in pairs:
            fp.write(pair[0] + "|" + pair[1] + "\n")


def _append_to_data_pool(csvfp: csv.DictReader, data_pool):
    """
    Simple helper method to append non-empty data rows to a list representing
    a pool of aggregated data.
    """
    for row in csvfp:
        # Minimum one column for numeric code, original code string, variants
        if len(row) >= 3:
            data_pool.append(row)


if __name__ == "__main__":
    generate_positive_pairs(BASE_FILE_PATH, -1, OUT_FILE_PATH)
