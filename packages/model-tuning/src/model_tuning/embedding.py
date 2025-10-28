import os
import pickle
import sys
from typing import List

import torch
from sentence_transformers import SentenceTransformer

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from utils.parse_and_extract_loinc_names import parse_snoinc_extracts

SNOINC_CODES_FILE = "../data/snoinc_extracts/loinc_lab_names_20251008.csv"
DATE = SNOINC_CODES_FILE.split("_")[-1].split(".")[0]
EMBEDDING_CACHE_DIR = "../data/training_files/embeddings/"

BATCH_SIZE = 32
CHUNK_SIZE = 8192


def embed_loinc_names(
    model: SentenceTransformer, name_list: List[str], dest: str, use_incremental_mini_batching=False
):
    """
    Use a SentenceTransformers model to embed the standard name codes for
    a given set of LOINC values. These embeddings form the "Vector DB" that
    will be used for semantic search on the examples-to-evaluate.

    :param model: The Sentence Transformers model to use for embedding.
    :param name_list: A list of strings to embed into the Vector DB.
    :param dest: A file name to save the embeddings into.
    :param use_incremental_mini_batching: Optionally, whether to incrementally
      write embedding vectors to disk as we go, or whether to perform the
      whole computation at once. Defaults to False, but set to True for
      large parameter models and large datasets.
    """
    # Make sure just the directory exists
    os.makedirs(EMBEDDING_CACHE_DIR, exist_ok=True)

    if use_incremental_mini_batching:
        # We'll iterate in chunk-sized intervals to not overload the GPU
        start = 0
        while start < len(name_list):
            end = min(start + CHUNK_SIZE, len(name_list))
            mini_batch = name_list[start:end]

            print("Mini-batching from", start, "to", end - 1)

            batch_embeddings: torch.Tensor = model.encode(
                mini_batch, batch_size=BATCH_SIZE, show_progress_bar=True, convert_to_tensor=True
            )
            batch_embeddings = batch_embeddings.to("cpu")
            try:
                # No direct appending to pickle file, so read it, extend it,
                # overwrite it. Torch.cat is super efficient so this isn't a
                # problem as long as we move to CPU.
                with open(EMBEDDING_CACHE_DIR + dest, "rb") as fp:
                    cache_data = pickle.load(fp)
                name_codes: List = cache_data["codes"]
                saved_embeddings: torch.Tensor = cache_data["embeddings"]
                name_codes.extend(mini_batch)
                extended_embeddings = torch.cat((saved_embeddings, batch_embeddings), dim=0)

                with open(EMBEDDING_CACHE_DIR + dest, "wb") as fp:
                    pickle.dump({"codes": name_codes, "embeddings": extended_embeddings}, fp)

            except FileNotFoundError:
                # File doesn't exist, so just create it
                with open(EMBEDDING_CACHE_DIR + dest, "wb") as fp:
                    pickle.dump({"codes": mini_batch, "embeddings": batch_embeddings}, fp)

            start += CHUNK_SIZE

    else:
        corpus_embeddings = model.encode(
            name_list, batch_size=BATCH_SIZE, show_progress_bar=True, convert_to_tensor=True
        )
        with open(EMBEDDING_CACHE_DIR + dest, "wb") as fp:
            pickle.dump({"codes": name_list, "embeddings": corpus_embeddings}, fp)


if __name__ == "__main__":
    models = [
        "Qwen/Qwen3-Embedding-0.6B",
    ]

    print("Extracting SNOINC data to form standardized names...")
    lcns, sns, dns = parse_snoinc_extracts(SNOINC_CODES_FILE)
    name_codes = lcns + sns + dns

    for mn in models:
        embedding_file = f"loinc_lab_names_{mn.replace('/', '_')}_{DATE}"

        print("Instantiating language model", mn)
        model = SentenceTransformer(mn)

        print("Performing embedding, this might take a while...")
        embeddings = embed_loinc_names(
            model, name_codes, embedding_file, use_incremental_mini_batching=True
        )
