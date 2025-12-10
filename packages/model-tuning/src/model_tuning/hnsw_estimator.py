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

# GRID-SEARCH ANN PARAMS
# EF-value is described as the "speed/accuracy" tradeoff metric for HNSW
# search. EF typically ranges from 50 to 1000, with a default value being
# 200. Higher values of EF will increase recall compared to exact search,
# (i.e. results will tend to look more like exact kNN), but will increase
# search time in a nonlinear fashion.
EF_CONSTRUCTION = 200
# M-Value is the number of connections/neighbors made per "node" in the
# search graph. It represents how many embedded vectors are considered to
# be in the "small world" defined around each other vector. Higher values
# of M increase recall compared to exact search, but also slow down
# the search time.
M_VALUE = 48
# These are the range of EF values we want to test during our grid search.
# The EF-value that an HNSW index is constructed with *does not* need to be
# the EF-value that index is searched with. The search EF can range from
# 0 to 1000, just like the initial EF used during construction. The initial
# EF controls how many "small worlds" get attached as branches in the
# search graph, while this "search EF" controls how many actually get
# explored by the algorithm during ANN.
EFS_TO_TEST = [50, 100, 200, 400, 600, 800, 1000]

# VALIDATION VARIABLES
VALIDATION_FILE = "../data/training_files/validation_set_positive_pairs.txt"
# This is the "k" value in KNN, how many approximate neighbors we'll be
# retrieving. The script does not optimize a search over K, but the choice of
# K does directly influence the ordered-recall calculation (e.g. more neighbors
# means a better sample to compare ANN to exact KNN).
NUM_NEIGHBORS_TO_SEARCH = 10

# IMPORTANT: Change this value to calculate stats using more or less
# examples drawn from the validation set.
NUM_EXAMPLES_TO_VALIDATE = 10000


def run_recall_trial(
    model: SentenceTransformer,
    hnsw_index: hnswlib.Index,
    bf_index: hnswlib.Index,
    examples: list[list[str]],
    k: int,
    ef: int,
) -> None:
    """Perform a single search in a grid of trials to compare approximate search
    with exact search. Importantly, the goal of a recall trial is *not* to
    maximize accuracy. Model analysis is a separate task. The goal of ANN
    hyperparameter optimization is to get the approximate search to behave
    as closely as possible to exact search in terms of which results are
    retrieved and the relative rankings of those results. This allows other
    notebooks to optimize for Top-K performance.

    :param model: The sentence transformers model to evaluate.
    :param hnsw_index: An HNSW index file computed over the embeddings.
    :param bf_index: A brute force index file computed over the embeddings.
    :param examples: A list of validation samples on which to evaluate recall.
    :param k: The number of search results to retrieve.
    :param ef: The search depth to use as part of this optimization.
    """
    num_correct = 0.0
    search_times = []

    for e in examples:
        nonstandard_in = e[1].strip()

        # Unlike embedding, which can convert to tensor on GPU, HNSW exists in
        # CPU memory, so we leave as is
        enc = model.encode(nonstandard_in)
        start = time.time()
        labels_hnsw, _ = hnsw_index.knn_query(enc, k=k)
        search_times.append(time.time() - start)
        labels_bf, _ = bf_index.knn_query(enc, k=k)

        for label in labels_hnsw[0]:
            for correct_label in labels_bf[0]:
                # We're counting only the instances where the elements between
                # HNSW and brute force match
                if label == correct_label:
                    num_correct += 1
                    break

    recall = round(num_correct / float(k * len(examples)), 3)
    mean_search_time = round(float(sum(search_times)) / float(len(search_times)), 3)

    print(f"Speed/Accuracy Tradeoff for K = {k}, EF = {ef}")
    print(f"  Recall: {recall}")
    print(f"  Mean Search Time: {mean_search_time}")


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

            print("Loading validation set...")
            examples = []
            with open(VALIDATION_FILE) as fp:
                for line in fp:
                    if line.strip() != "":
                        examples.append(line.strip().split("|"))
            random.shuffle(examples)
            examples = examples[:NUM_EXAMPLES_TO_VALIDATE]

            print("Initializing Indices: Regular and Brute Force")
            hnsw_index = hnswlib.Index(space="cosine", dim=EMBEDDING_SIZE)
            bf_index = hnswlib.BFIndex(space="cosine", dim=EMBEDDING_SIZE)
            hnsw_index.init_index(
                max_elements=len(embeddings),
                ef_construction=EF_CONSTRUCTION,
                M=M_VALUE,
            )
            bf_index.init_index(max_elements=len(embeddings))

            hnsw_index.add_items(embeddings)
            bf_index.add_items(embeddings)

            print("Performing grid-search on EF to identify optimal value...")
            for ef in EFS_TO_TEST:
                hnsw_index.set_ef(ef)
                run_recall_trial(model, hnsw_index, bf_index, examples, NUM_NEIGHBORS_TO_SEARCH, ef)

    else:
        print("No embeddings found, please run embedding.py to compute vectors first.")
