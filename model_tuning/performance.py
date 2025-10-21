import os
import pickle
import random
import time
from typing import List

from sentence_transformers import SentenceTransformer
from sentence_transformers import util
from torch import Tensor

MODEL_NAME = "intfloat/e5-base-v2"
EMBEDDING_CACHE_DIR = "../data/training_files/embeddings/"
EMBEDDING_FILE = "loinc_lab_names_intfloat_e5-base-v2_20251007"
VALIDATION_FILE = "../data/training_files/validation_set_positive_pairs.txt"
K_VALUES = [1, 3, 5, 10]

# IMPORTANT: Change this value to calculate stats using more or less
# examples drawn from the validation set.
NUM_EXAMPLES_TO_VALIDATE = 1000


def predict_and_evaluate_validation_set(
    model: SentenceTransformer,
    vector_db: Tensor,
    standard_loinc_names: List[str],
    examples: List[List[str]],
    k_vals: List[int],
) -> None:
    """
    Compute performance statistics for a given model on a given set of validation
    data. The data is expected to be a list of lists in which the first element
    of each pair is the trial nonstandard free-text input, and the second element
    is the standardized code that should be mapped to. Computed statistics include
    Top-K accuracy for the given value of K, mean cosine similarity of the highest
    scoring result, and mean time to encode an input and perform semantic search.

    :param model: The sentence transformer model to evaluate.
    :param vector_db: A list of pre-computed embeddings on the corpus in which
      to semantic search (these are the embedded standard LOINC codes).
    :param standard_loinc_names: A list of strings representing the names of
      the LOINC codes embedded in the `vector_db`. Note that the order of
      strings in the list should match the order of embeddings in the DB.
    :param examples: A list of lists of strings representing the experimental
      examples to evaluate.
    :param k: An integer for how many neighbors to retrieve from the DB.
    :returns: None
    """
    encoding_times = []
    cosine_sims = {k: [] for k in k_vals}
    times = {k: [] for k in k_vals}
    examples_with_correct_output_in_top_k = {k: 0.0 for k in k_vals}

    random.shuffle(examples)
    examples = examples[:NUM_EXAMPLES_TO_VALIDATE]

    for e in examples:
        correct_code = e[0].strip()
        nonstandard_in = e[1].strip()

        # This utility performs exact neighbor semantic search
        # If approximate is desired, see
        # https://sbert.net/examples/sentence_transformer/applications/semantic-search/README.html#approximate-nearest-neighbor     # noqa
        # for details
        start = time.time()
        enc = model.encode(nonstandard_in, convert_to_tensor=True)
        encoding_times.append(time.time() - start)

        for k in k_vals:
            start = time.time()
            hits = util.semantic_search(enc, vector_db, top_k=k)
            hits = hits[0]

            # Store some metrics
            times[k].append(time.time() - start)
            cosine_sims[k].append(hits[0]["score"])

            # Check if correct answer is in the returned search results
            correct_in_top_k = False
            for h in hits:
                mapped_sentence = standard_loinc_names[h["corpus_id"]]  # ty: ignore
                if mapped_sentence == correct_code:
                    correct_in_top_k = True
                    break
            if correct_in_top_k:
                examples_with_correct_output_in_top_k[k] += 1.0

    mean_encoding_time = round(float(sum(encoding_times)) / float(len(encoding_times)), 3)
    print(f"  Mean Encoding Time: {mean_encoding_time} seconds")

    for k in k_vals:
        mean_cosine_sim = round(float(sum(cosine_sims[k])) / float(len(cosine_sims[k])), 3)
        mean_encoding_search_time = round(float(sum(times[k])) / float(len(times[k])), 3)
        top_k_accuracy = round(examples_with_correct_output_in_top_k[k] / float(len(examples)), 5)

        print(f"  Trial: Value for Top-K at K = {k}")

        print(f"    Top-K Accuracy: {top_k_accuracy * 100.0}%")
        print(f"    Mean Cosine Similarity: {mean_cosine_sim}")
        print(f"    Mean Search Time: {mean_encoding_search_time}")


if __name__ == "__main__":
    print("Instantiating language model...")
    model = SentenceTransformer(MODEL_NAME)

    print("Checking for cached embeddings...")
    if os.path.exists(EMBEDDING_CACHE_DIR + EMBEDDING_FILE):
        print("  Found cached embeddings. Loading them...")
        with open(EMBEDDING_CACHE_DIR + EMBEDDING_FILE, "rb") as fp:
            cache_data = pickle.load(fp)
            name_codes = cache_data["codes"]
            embeddings = cache_data["embeddings"]

            print("Loading validation set...")
            examples = []
            with open(VALIDATION_FILE, "r") as fp:
                for line in fp:
                    if line.strip() != "":
                        examples.append(line.strip().split("|"))

            print("Predicting and computing stats for validation set...")
            predict_and_evaluate_validation_set(model, embeddings, name_codes, examples, K_VALUES)

    else:
        print("No embeddings found, please run embedding.py to compute vectors first.")
