import json
import os
import pickle

import numpy as np
import torch

CHUNK_SIZE = 1000

# Script to convert LOINC embedding pickle files to JSONL files
# Sample usage:
# python3 packages/model-tuning/src/model_tuning/jsonl_converter.py

# Download embedding file from Google Docs and process to JSONL files - https://drive.google.com/drive/u/0/folders/1PNU9KXak5l1b5bzmJDbx17jq3A_THhsy
input_file = "/Users/rob/Downloads/loinc_lab_names_Qwen_Qwen3-Embedding-0.6B_20251008"
model = input_file.split("/")[-1]


def open_embedding_file(input_file: str) -> dict:
    """
    Opens a pickle file containing embeddings.
    TODO: do we need to use Google Docs API here instead?
    :param input_file: Path to the pickle file containing embeddings.
    """
    with open(input_file, "rb") as f:
        data = pickle.load(f)
        return data


def clean_embedding_data(data: dict) -> tuple[dict, np.ndarray]:
    """
    Cleans the embedding data by ensuring embeddings are in numpy array format.
    :param data: Dictionary containing codes and embeddings.
    """
    codes = data["codes"]
    embeddings = data["embeddings"]
    # Convert to numpy if tensor
    if isinstance(embeddings, torch.Tensor):
        print("Converting embeddings from torch.Tensor to numpy array")
        embeddings = embeddings.cpu().numpy()
    return codes, embeddings


def write_jsonl_files(codes: list, embeddings: np.ndarray, model: str, chunk_size=CHUNK_SIZE):
    """
    Writes the codes and embeddings to JSONL files in chunks.
    :param codes: List of LOINC standard names.
    :param embeddings: Numpy array of embeddings.
    :param model: Model name used in the output file names.
    :param chunk_size: Number of entries per JSONL file.
    """
    output_folder = os.path.join(os.getcwd(), "data", "training_files", "embeddings", model)
    os.makedirs(output_folder, exist_ok=True)
    print(f"Converting model {model}")

    for i in range(0, len(codes), chunk_size):
        chunk = [
            {
                "id": str(i + j),
                "description": codes[i + j],
                "descriptionVector": embeddings[i + j].tolist(),
            }
            for j in range(min(chunk_size, len(codes) - i))
        ]
        with open(f"{output_folder}/{model}_{i // chunk_size:05d}.jsonl", "w") as f:
            for doc in chunk:
                f.write(json.dumps(doc) + "\n")

        print(f"Wrote chunk {i // CHUNK_SIZE}")


if __name__ == "__main__":
    data = open_embedding_file(input_file)
    codes, embeddings = clean_embedding_data(data)
    write_jsonl_files(codes, embeddings, model)
