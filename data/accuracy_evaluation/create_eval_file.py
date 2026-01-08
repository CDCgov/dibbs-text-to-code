import json
import os

import requests
from dotenv import load_dotenv

load_dotenv()

USERNAME = os.environ.get("LOINC_USERNAME")
PASSWORD = os.environ.get("LOINC_PASSWORD")

url = "https://loinc.regenstrief.org/searchapi/loincs"


def search_loinc(raw_query: str):
    """
    Searches the LOINC database using the provided raw query string.
    :param raw_query: The raw query string to search for in the LOINC database.
    """
    params = {"query": f'"{raw_query}"'}
    response = requests.get(
        url,
        params=params,
        auth=(USERNAME, PASSWORD),
        timeout=30,
    )
    return response.json()


file_path = "data/accuracy_evaluation/eval_results_snippet.jsonl"
with open(file_path, "r") as f:
    raw_eval_data = [json.loads(line) for line in f if line.strip()]

loinc_dict = {}
# build loinc dictionary for caching
for item in raw_eval_data:
    if item.get("expected_label") not in loinc_dict.keys():
        search = search_loinc(item.get("expected_label"))
        loinc_dict[item.get("expected_label")] = (
            search.get("Results")[0].get("LOINC_NUM")
            if search.get("ResponseSummary").get("RowsReturned") == 1
            else None
        )
    for result in item.get("results"):
        if result.get("label") not in loinc_dict.keys():
            search = search_loinc(result.get("label"))
            loinc_dict[result.get("label")] = (
                search.get("Results")[0].get("LOINC_NUM")
                if search.get("ResponseSummary").get("RowsReturned") == 1
                else None
            )

eval_data = []
for item in raw_eval_data:
    grouped_row = {
        "example_idx": item.get("example_idx"),
        "k-run": item.get("k"),
        "raw_text": item.get("query_input"),
        "expected_text": item.get("expected_label"),
        "expected_loinc": loinc_dict.get(item.get("expected_label")),
        "results": [],
    }
    for result in item.get("results"):
        grouped_row["results"].append(
            {
                "id": str(item.get("example_idx"))
                + "_"
                + str(item.get("k"))
                + "_"
                + str(result.get("rank")),
                "rank": result.get("rank"),
                "returned_text": result.get("label"),
                "returned_loinc": loinc_dict.get(result.get("label")),
            }
        )
    eval_data.append(grouped_row)

with open(
    "data/accuracy_evaluation/eval_results_snippet_with_codes.txt",
    "w",
) as f:
    json.dump(eval_data, f, indent=2)
