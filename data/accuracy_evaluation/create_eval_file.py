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


file_path = (
    "/Users/rob/dibbs-text-to-code/data/accuracy_evaluation/eval_results_snippet_with_codes.jsonl"
)
with open(file_path, "r") as f:
    raw_eval_data = [json.loads(line) for line in f if line.strip()]

eval_data = []
for item in raw_eval_data:
    expected_loinc = search_loinc(item.get("expected_label"))
    returned_loinc = search_loinc(item.get("top_predicted").get("label"))
    eval_data.append(
        {
            "id": str(item.get("example_idx")) + "_" + str(item.get("k")),
            "raw_text": item.get("query_input"),
            "expected_text": item.get("expected_label"),
            "returned_text": item.get("top_predicted").get("label"),
            "expected_loinc": expected_loinc.get("Results")[0].get("LOINC_NUM")
            if expected_loinc.get("ResponseSummary").get("RowsReturned") == 1
            else None,
            "returned_loinc": returned_loinc.get("Results")[0].get("LOINC_NUM")
            if returned_loinc.get("ResponseSummary").get("RowsReturned") == 1
            else None,
        }
    )

# pop the rows for now that have no loinc for sake of testing
eval_data = [
    item
    for item in eval_data
    if item.get("expected_loinc") is not None and item.get("returned_loinc") is not None
]

with open(
    "/Users/rob/dibbs-text-to-code/data/accuracy_evaluation/eval_results_snippet_with_codes.txt",
    "w",
) as f:
    json.dump(eval_data, f, indent=2)
