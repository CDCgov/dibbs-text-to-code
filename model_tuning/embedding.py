import os
import pickle
from typing import List

import torch
from sentence_transformers import SentenceTransformer

SNOINC_CODES_FILE = "../data/snoinc_extracts/loinc_lab_names_20251008.csv"
# use date in filename to keep track of versions
DATE = SNOINC_CODES_FILE.split("_")[-1].split(".")[0]
EMBEDDING_CACHE_DIR = "../data/training_files/embeddings/"

CHUNK_SIZE = 1024


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

    with open(extract_path, "r", encoding="utf-8") as fp:
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


def embed_loinc_names(model: SentenceTransformer, name_list: List[str], dest: str):
    """
    Use a SentenceTransformers model to embed the standard name codes for
    a given set of LOINC values. These embeddings form the "Vector DB" that
    will be used for semantic search on the examples-to-evaluate.

    :param model: The Sentence Transformers model to use for embedding.
    :param name_list: A list of strings to embed into the Vector DB.
    :param dest: A file name to save the embeddings into.
    """
    # make sure just the directory exists
    os.makedirs(EMBEDDING_CACHE_DIR, exist_ok=True)

    start = 0
    while start < len(name_list):
        end = min(start + CHUNK_SIZE, len(name_list))
        mini_batch = name_list[start:end]

        print("Mini-batching from", start, "to", end - 1)

        batch_embeddings: torch.Tensor = model.encode(
            mini_batch, batch_size=64, show_progress_bar=True, convert_to_tensor=True
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


if __name__ == "__main__":
    models = [
        "ibm-granite/granite-embedding-125m-english",
        "intfloat/e5-large-v2",
        "BAAI/bge-large-en-v1.5",
    ]

    print("Extracting SNOINC data to form standardized names...")
    lcns, sns, dns = parse_snoinc_extracts(SNOINC_CODES_FILE)
    name_codes = lcns + sns + dns

    for mn in models:
        embedding_file = f"loinc_lab_names_{mn.replace('/', '_')}_{DATE}"

        print("Instantiating language model", mn)
        model = SentenceTransformer(mn)

        print("Performing embedding, this might take a while...")
        embeddings = embed_loinc_names(model, name_codes, embedding_file)
