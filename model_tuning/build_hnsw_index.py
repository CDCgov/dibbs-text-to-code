"""
build_hnsw_index.py


Simple script for creating an HNSW index for a specific set of model
vector embeddings. This index can be persisted to disk for faster
instantiation during performance metric computation.
"""

import os
import pickle

import hnswlib

# MODEL VARIABLES
MODEL_NAME = "intfloat/e5-base-v2"
EMBEDDING_SIZE = 768

# EMBEDDING VARIABLES
EMBEDDING_CACHE_DIR = "../data/training_files/embeddings/"
EMBEDDING_FILE = "loinc_lab_names_intfloat_e5-base-v2_20251007"

# ANN INDEX VARIABLES
INDEX_DIR = "../data/training_files/hnsw_indices/"
INDEX_FP = f"hnswlib_index_{MODEL_NAME.replace('/', '_')}.index"
EF_VALUE = 200
M_VALUE = 64


if __name__ == "__main__":
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
            if os.path.exists(INDEX_DIR + INDEX_FP):
                print("  Cached index already exists.")
            else:
                print(f"No local index found. Creating index for {MODEL_NAME}...")
                index.init_index(max_elements=len(embeddings), ef_construction=EF_VALUE, M=M_VALUE)
                print("  Index created, adding vectors...")
                index.add_items(embeddings, list(range(len(embeddings))))
                print("  Vectors embedded, saving index...")
                index.save_index(INDEX_DIR + INDEX_FP)
    else:
        print("No embeddings found, please run embedding.py to compute vectors first.")
