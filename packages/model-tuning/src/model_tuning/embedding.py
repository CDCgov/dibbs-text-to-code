import json
import os
import sys
from typing import List

import torch
from sentence_transformers import SentenceTransformer

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from utils.parse_and_extract_loinc_names import parse_snoinc_extracts

EMBEDDING_CACHE_DIR = os.getcwd() + "/data/training_files/embeddings/"

BATCH_SIZE = 32
CHUNK_SIZE = 8192
JSONL_CHUNK_SIZE = 1000
MODELS = [
    # "intfloat/e5-base-v2",
    # "intfloat/e5-large-v2",
    # "BAAI/bge-base-en-v1.5",
    # "BAAI/bge-large-en-v1.5",
    # "Snowflake/snowflake-arctic-embed-l-v2.0",
    # "Qwen/Qwen3-Embedding-4B",
]


def get_snoinc_file_path(file_path: str) -> str:
    """
    Returns the path to the SNOINC codes file.
    """
    # Get the newest file in the snoinc_extracts directory
    snoinc_dir = file_path
    files = os.listdir(snoinc_dir)
    snoinc_files = [f for f in files if f.startswith("loinc_lab_names_") and f.endswith(".csv")]
    snoinc_files.sort(reverse=True)
    if not snoinc_files:
        raise FileNotFoundError("No SNOINC codes file found in the snoinc_extracts directory.")
    SNOINC_CODES_FILE = os.path.join(snoinc_dir, snoinc_files[0])

    return SNOINC_CODES_FILE


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

    model_dir = os.path.join(EMBEDDING_CACHE_DIR, dest)
    os.makedirs(model_dir, exist_ok=True)

    current_chunk = []
    chunk_index = 0

    def flush_chunk():
        nonlocal current_chunk, chunk_index
        if not current_chunk:
            return
        chunk_index += 1
        chunk_filename = os.path.join(
            model_dir,
            f"{dest}_embeddings_chunk_{chunk_index:04d}.jsonl",
        )
        with open(chunk_filename, "w") as f:
            for doc in current_chunk:
                f.write(json.dumps(doc) + "\n")
        print(f"Wrote JSONL chunk {chunk_index}")
        current_chunk = []

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

            for idx, code in enumerate(mini_batch):
                global_index = start + idx
                current_chunk.append(
                    {
                        "id": str(global_index),
                        "description": code,
                        "descriptionVector": batch_embeddings[idx].tolist(),
                    }
                )
                if len(current_chunk) >= JSONL_CHUNK_SIZE:
                    flush_chunk()

            start += CHUNK_SIZE

        flush_chunk()

    else:
        corpus_embeddings = model.encode(
            name_list, batch_size=BATCH_SIZE, show_progress_bar=True, convert_to_tensor=True
        )
        corpus_embeddings = corpus_embeddings.to("cpu")

        for i, code in enumerate(name_list):
            current_chunk.append(
                {
                    "id": str(i),
                    "description": code,
                    "descriptionVector": corpus_embeddings[i].tolist(),
                }
            )
            if len(current_chunk) >= JSONL_CHUNK_SIZE:
                flush_chunk()

        flush_chunk()


if __name__ == "__main__":
    SNOINC_CODES_FILE = get_snoinc_file_path(os.getcwd() + "/data/snoinc_extracts/")
    DATE = SNOINC_CODES_FILE.split("_")[-1].split(".")[0]
    print(f"Extracting {DATE} SNOINC data to form standardized names...")
    lcns, sns, dns = parse_snoinc_extracts(SNOINC_CODES_FILE)
    name_codes = lcns + sns + dns

    for mn in MODELS:
        model_name_safe = mn.replace("/", "_")
        embedding_prefix = f"loinc_lab_names_{model_name_safe}_{DATE}"

        print("Instantiating language model", mn)
        model = SentenceTransformer(mn)

        print("Performing embedding, this might take a while...")
        embed_loinc_names(model, name_codes, embedding_prefix, use_incremental_mini_batching=True)
