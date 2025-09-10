import os
import pickle
import time
from typing import List

from sentence_transformers import SentenceTransformer
from sentence_transformers import util
from torch import Tensor

MODEL_NAME = "all-MiniLM-L6-v2"
SNOINC_CODES_FILE = "snoinc_data_extracts/loinc_lab_names.csv"
EMBEDDING_CACHE_DIR = "embeddings/"
EMBEDDING_FILE = f"loinc_lab_names_{MODEL_NAME.replace('/', '_')}"
VALIDATION_FILE = "data/validation_toy.txt"
K_VALUES = [1, 3, 5, 10]


def parse_snoinc_extracts(
    extract_path: str,
    short_name_col: int = 1,
    long_name_col: int = 2,
    display_name_col: int = 3,
    skip_first: bool = True,
):
    """
    Given a path to an extract file of information on various LOINC codes,
    parse the rows of that file in to three discrete lists corresponding to
    the long common names, short names, and display names of those codes.
    The file is expected to be a pipe-delimited text file in which each
    LOINC code is expected to represent a single line.

    :param extract_path: The path to the extract file to parse.
    :param short_name_col: The column of the pipe file containing the
      short name for a given LOINC code.
    :param long_name_col: The column of the pipe file containing the long
      common name for a given LOINC code.
    :param display_name_col: The column of the pipe file containing the
      display name for a given LOINC code.
    :param skip_first: Optionally, a boolean indicating whether to skip the
      first line of the file, if it is a header row.
    :returns: A tuple of three lists, one for eaech name variant.
    """
    long_common_names = []
    short_names = []
    display_names = []

    with open(extract_path, "r") as fp:
        lines_seen = 0
        for line in fp:
            if lines_seen == 0:
                lines_seen += 1
                if skip_first:
                    continue
            if line.strip() != "":
                names = line.strip().split("|")
                # Skip lines that aren't real entries (formatting artifacts)
                if len(names) >= 4:
                    long_common_names.append(names[long_name_col].strip())
                    short_names.append(names[short_name_col].strip())
                    display_names.append(names[display_name_col].strip())

    for name_list in [long_common_names, short_names, display_names]:
        name_list = [x for x in name_list if not x == ""]

    return long_common_names, short_names, display_names


def embed_loinc_names(
    model: SentenceTransformer, name_list: List[str], save_embeddings: bool = False
):
    """
    Use a SentenceTransformers model to embed the standard name codes for
    a given set of LOINC values. These embeddings form the "Vector DB" that
    will be used for semantic search on the examples-to-evaluate. Optionally,
    save the embeddings to disk since computing them is time-consuming.

    :param model: The Sentence Transformers model to use for embedding.
    :param name_list: A list of strings to embed into the Vector DB.
    :param save_embeddings: Optionally, a boolean in dicating whether to persist
      the computed embeddings to disk.
    :returns: The computed embeddings.
    """
    name_list = name_list[:10000]
    corpus_embeddings = model.encode(name_list, show_progress_bar=True, convert_to_tensor=True)

    if save_embeddings:
        with open(EMBEDDING_CACHE_DIR + EMBEDDING_FILE, "wb") as fp:
            pickle.dump({"codes": name_list, "embeddings": corpus_embeddings}, fp)

    return corpus_embeddings


def predict_and_evaluate_validation_set(
    model: SentenceTransformer,
    vector_db: Tensor,
    standard_loinc_names: List[str],
    examples: List[List[str]],
    k: int,
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
    cosine_sims = []
    times = []
    examples_with_correct_output_in_top_k = 0.0

    for e in examples:
        nonstandard_in = e[0].strip()
        correct_code = e[1].strip()

        # This utility performs exact neighbor semantic search
        # If approximate is desired, see
        # https://sbert.net/examples/sentence_transformer/applications/semantic-search/README.html#approximate-nearest-neighbor     # noqa
        # for details
        start = time.time()
        enc = model.encode(nonstandard_in, convert_to_tensor=True)
        hits = util.semantic_search(enc, vector_db, top_k=k)
        hits = hits[0]

        # Store some metrics
        times.append(time.time() - start)
        cosine_sims.append(hits[0]["score"])

        # Check if correct answer is in the returned search results
        correct_in_top_k = False
        for h in hits:
            mapped_sentence = standard_loinc_names[h["corpus_id"]]  # ty: ignore
            if mapped_sentence == correct_code:
                correct_in_top_k = True
                break
        if correct_in_top_k:
            examples_with_correct_output_in_top_k += 1.0

    mean_cosine_sim = round(float(sum(cosine_sims)) / float(len(cosine_sims)), 3)
    mean_encoding_search_time = round(float(sum(times)) / float(len(times)), 3)
    top_k_accuracy = round(examples_with_correct_output_in_top_k / float(len(examples)), 5)

    print(f"    Top-K Accuracy: {top_k_accuracy * 100.0}%")
    print(f"    Mean Cosine Similarity: {mean_cosine_sim}")
    print(f"    Mean Search Time: {mean_encoding_search_time}")


if __name__ == "__main__":
    print("Instantiating language model...")
    model = SentenceTransformer(MODEL_NAME)

    print("Extracting SNOINC data to form standardized names...")
    lcns, sns, dns = parse_snoinc_extracts(SNOINC_CODES_FILE)

    print("Checking for cached embeddings...")
    if os.path.exists(EMBEDDING_CACHE_DIR + EMBEDDING_FILE):
        print("  Found cached embeddings. Loading them...")
        with open(EMBEDDING_CACHE_DIR + EMBEDDING_FILE, "rb") as fp:
            cache_data = pickle.load(fp)
            name_codes = cache_data["codes"]
            embeddings = cache_data["embeddings"]
    else:
        print("No cache found, performing embedding.")
        name_codes = lcns + sns + dns
        print("  This might take a while...")
        embeddings = embed_loinc_names(model, name_codes, save_embeddings=True)

    print("Loading validation set...")
    examples = []
    with open(VALIDATION_FILE, "r") as fp:
        for line in fp:
            if line.strip() != "":
                examples.append(line.split("|"))

    print("Predicting and computing stats for validation set...")
    for k in K_VALUES:
        print(f"  Trial: Value for Top-K is {k}")
        predict_and_evaluate_validation_set(model, embeddings, name_codes, examples, k)
