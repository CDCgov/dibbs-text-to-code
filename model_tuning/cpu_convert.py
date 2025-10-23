"""
cpu_convert.py


Simple script for converting collections of embedded vectors that were
built using GPU / Tensor optimization to purely CPU-compatible.

Vector embeddings *must* be CPU-formatted for use with Azure ML Studio's
copy of the `performance.ipynb` notebook.
"""

import pickle

# Directory in which the embeddings are saved
EMBEDDING_CACHE_DIR = "../data/training_files/embeddings/"

# The original embedding file that may have been saved in a GPU-based
# format
GPU_PICKLE_FILE = "loinc_lab_names_intfloat_e5-base-v2_20251007"

# The new embedding file to write after conversion to pure CPU formatting
CPU_PICKLE_FILE = "loinc_lab_names_intfloat_e5-base-v2_20251007_cpu"


if __name__ == "__main__":
    print("Loading pickled tensor embeddings...")
    with open(EMBEDDING_CACHE_DIR + GPU_PICKLE_FILE, "rb") as fp:
        cache_data = pickle.load(fp)
    name_codes = cache_data["codes"]
    embeddings = cache_data["embeddings"]

    print("Converting to CPU and writing back...")
    embeddings = embeddings.cpu()
    with open(EMBEDDING_CACHE_DIR + CPU_PICKLE_FILE, "wb") as fp:
        pickle.dump({"codes": name_codes, "embeddings": embeddings}, fp)
