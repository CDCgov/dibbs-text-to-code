import os
import pickle
import random
import time

import hnswlib
from sentence_transformers import SentenceTransformer

# MODEL VARIABLES
MODEL_NAME = "intfloat/e5-base-v2"
EMBEDDING_SIZE = 768

# EMBEDDING VARIABLES
EMBEDDING_CACHE_DIR = "../data/training_files/embeddings/"
EMBEDDING_FILE = "loinc_lab_names_intfloat_e5-base-v2_20251007"

# ANN INDEX VARIABLES
INDEX_FP = "./hnswlib.index"
EF_CONSTRUCTION = 200
M_VALUE = 64
EF_SEARCH = 100

# VALIDATION VARIABLES
VALIDATION_FILE = "../data/training_files/validation_set_positive_pairs.txt"
K_VALUES = [1, 3, 5, 10]

# IMPORTANT: Change this value to calculate stats using more or less
# examples drawn from the validation set.
NUM_EXAMPLES_TO_VALIDATE = 1000


def predict_and_evaluate_validation_set(
    model: SentenceTransformer,
    ann_index: hnswlib.Index,
    standard_loinc_names: list[str],
    examples: list[list[str]],
    k_vals: list[int],
) -> None:
    """Compute performance statistics for a given model on a given set of validation
    data. The data is expected to be a list of lists in which the first element
    of each pair is the trial nonstandard free-text input, and the second element
    is the standardized code that should be mapped to. Computed statistics include
    Top-K accuracy for the given value of K, mean cosine similarity of the highest
    scoring result, and mean time to encode an input and perform semantic search.

    :param model: The sentence transformer model to evaluate.
    :param ann_index: A pre-computed HNSW index file over the embeddings that
      we want to match nonstandard inputs to.
    :param standard_loinc_names: A list of strings representing the names of
      the LOINC codes embedded in the `vector_db`. Note that the order of
      strings in the list should match the order of embeddings in the DB.
    :param examples: A list of lists of strings representing the experimental
      examples to evaluate.
    :param k_vals: A list of integers indicating how many neighbors should be
      retrieved from the DB across a range of trials.
    :returns: None
    """
    encoding_times = []
    cosine_sims = {k: [] for k in k_vals}
    times = {k: [] for k in k_vals}
    examples_with_correct_output_in_top_k = dict.fromkeys(k_vals, 0.0)

    random.shuffle(examples)
    examples = examples[:NUM_EXAMPLES_TO_VALIDATE]

    for e in examples:
        correct_code = e[0].strip()
        nonstandard_in = e[1].strip()

        start = time.time()
        enc = model.encode(nonstandard_in)
        encoding_times.append(time.time() - start)

        for k in k_vals:
            start = time.time()
            embedding_ids, distances = ann_index.knn_query(enc, k=k)
            hits = [
                {"corpus_id": id, "score": 1 - dist}
                for id, dist in zip(embedding_ids[0], distances[0])
            ]
            hits = sorted(hits, key=lambda x: x["score"], reverse=True)

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
            embeddings = embeddings.cpu().numpy()

            index = hnswlib.Index(space="cosine", dim=EMBEDDING_SIZE)
            print("Checking for cached ANN index...")
            if os.path.exists(INDEX_FP):
                print("  Found cached index. Loading it...")
                index.load_index(INDEX_FP)
            else:
                print("No locally cached index found. Creating hierarchical index...")
                index.init_index(
                    max_elements=len(embeddings),
                    ef_construction=EF_CONSTRUCTION,
                    M=M_VALUE,
                )
                index.add_items(embeddings, list(range(len(embeddings))))
                index.save_index(INDEX_FP)
            index.set_ef(EF_SEARCH)

            print("Loading validation set...")
            examples = []
            with open(VALIDATION_FILE) as fp:
                for line in fp:
                    if line.strip() != "":
                        examples.append(line.strip().split("|"))

            print("Predicting and computing stats for validation set...")
            predict_and_evaluate_validation_set(
                model,
                index,
                embeddings,
                name_codes,
                examples,
                K_VALUES,
            )

    else:
        print("No embeddings found, please run embedding.py to compute vectors first.")
