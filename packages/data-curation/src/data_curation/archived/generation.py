import csv
import json
import random

# sample run: python3 packages/data-curation/src/data_curation/generation.py
BASE_FILE_PATH = "../../../../data/training_files/soft_lambda_loss_positives"
OUT_FILE_PATH = "../../../../data/training_files/soft_lambda_loss_positive_pairs.txt"
OUT_FILE_PATH_60K = "data/training_files/validation_set_60k_pairs.txt"
OUT_FILE_PATH_ERSD = "data/training_files/validation_set_ersd_pairs.txt"

loinc_file = "data/accuracy_evaluation/loinc_to_oids.txt"


def generate_positive_pairs(
    file_handle: str,
    num_codes_to_generate: int,
    out_file: str,
    num_samples_per_code: int = 1,
    rckms: bool = False,
) -> None:
    """Given the location of one or more files of LOINC codes and some corresponding augmented examples for those codes, this function compiles a list of positive pairs that can be read for model training. A positive pair is a tuple of the form (original_loinc_code, augmented_example_of_code).

    :param file_handle: Either the path to a specific file of LOINC codes and
      examples, or the prefix path for multiple data files across name variants.
    :param num_codes_to_generate: The number of LOINC codes to generate positive
      pairs for. If -1, one positive pair will be created for every LOINC code
      in the pool spanned by the files accessible via the handle parameter (e.g.
      if three name variant files are accessible, each LOINC code will appear
      in each file, thus each LOINC code will have one positive pair generated
      for each of its three name variants).
    :param out_file: The destination at which to write the positive pair file.
    :param num_samples_per_code: Optionally, how many sample nonstandard inputs
      should be generated for each of the LOINC codes to generate pairs for. If
      -1, then all augmentation possibilities included in all spanned files will
      be used as pairs.
    :param rckms: Whether the output LOINCs should be trigger codes for RCKMS.
    :returns: None
    """
    handle_parts = file_handle.split(".")
    data_pool = []
    pairs = []

    # Given handle is a prefix to multiple files, so we'll use naming
    # conventions to open the three appropriate ones
    if len(handle_parts) == 0 or handle_parts[-1] != "txt":
        for variant in ["long_common_name.csv", "short_name.csv", "display_name.csv"]:
            with open(file_handle + "_" + variant) as csvfp:
                rows = csv.reader(csvfp, delimiter=":")
                _append_to_data_pool(rows, data_pool)

    # Handle is actually a file, can just open that
    else:
        with open(file_handle) as csvfp:
            rows = csv.reader(csvfp, delimiter=":")
            _append_to_data_pool(rows, data_pool)

    if rckms:
        # Load in the set of LOINC codes that are RCKMS trigger codes
        rckms_loincs = []
        with open(loinc_file) as f:
            loinc = json.load(f)
            for code in loinc:
                rckms_loincs.append(code)

        # Filter the data pool to only include those codes
        data_pool = [element for element in data_pool if element[0].strip() in rckms_loincs]

    # Pre-specified number of examples to generate
    # If num_examples is -1, that's "generate all" mode, where we
    # produce one positive pair per code in the data pool, but we
    # can achieve that just by not truncating the pool list
    if num_codes_to_generate != -1:
        random.shuffle(data_pool)
        data_pool = data_pool[:num_codes_to_generate]

    for element in data_pool:
        loinc_code = element[0].strip()
        canonical_name = element[1].strip()
        possible_examples = element[2].strip()

        # Select specified number of pairs for each LOINC code in the
        # data pool. If it's -1, we'll just use all the generated options.
        if num_samples_per_code == -1:
            pairs.append((loinc_code, canonical_name, possible_examples))
        else:
            augmented_examples = possible_examples.split("|")
            chosen_ex = random.sample(augmented_examples, num_samples_per_code)
            chosen_ex = [x.strip() for x in chosen_ex]
            chosen_ex = "|".join(chosen_ex)
            pairs.append((loinc_code, canonical_name, chosen_ex.strip()))

    # Now we just write the created examples to the output file
    with open(out_file, "w") as fp:
        fp.writelines(pair[0] + "|" + pair[1] + "|" + pair[2] + "\n" for pair in pairs)


def _append_to_data_pool(csvfp: csv.DictReader, data_pool) -> None:
    """Simple helper method to append non-empty data rows to a list representing a pool of aggregated data."""
    for row in csvfp:
        # Minimum one column for numeric code, original code string, variants
        if len(row) >= 3:
            data_pool.append(row)


if __name__ == "__main__":
    generate_positive_pairs(BASE_FILE_PATH, -1, OUT_FILE_PATH, num_samples_per_code=-1)
    generate_positive_pairs(BASE_FILE_PATH, 60000, OUT_FILE_PATH_60K)
    generate_positive_pairs(BASE_FILE_PATH, 20000, OUT_FILE_PATH_ERSD, rckms=True)
