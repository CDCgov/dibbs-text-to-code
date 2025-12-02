import json
import os

import requests
from dotenv import load_dotenv

load_dotenv()

# sample run: python data/accuracy_evaluation/build_eval_files.py
# TES API Key can be obtained at https://tes.tools.aimsplatform.org/
TES_API_KEY = os.environ.get("TES_API_KEY")
TES_BASE_URL = "https://tes.tools.aimsplatform.org/api/fhir/ValueSet/"
TES_ENDPOINTS = ["lrtc", "lotc"]  # Endpoints for LOINC-related value sets

headers = {"x-api-key": TES_API_KEY, "Accept": "application/fhir+json"}


# Fetch LOINC value sets from TES API
def get_ersd_valuesets(endpoints: list) -> set:
    """
    Fetches LOINC value sets from TES API endpoints.
    :param endpoints: List of TES API endpoints to fetch value sets from.
    """
    oids = set()
    for endpoint in endpoints:
        url = f"{TES_BASE_URL}{endpoint}"
        response = requests.get(url, headers=headers)
        for oid in response.json().get("compose").get("include"):
            oids.add(oid.get("valueSet")[0].split("/")[-1])
    return oids


# Map conditions to OIDs and LOINC codes to OIDs
def build_mapping_files(oids: set) -> tuple[dict, dict]:
    """
    Builds mapping files for OIDs to conditions and LOINC codes to OIDs.
    :param oids: Set of OIDs to build mappings for.
    """
    oid_to_conditions = {}
    loinc_to_oids = {}
    for oid in oids:
        url = f"{TES_BASE_URL}{oid}"
        response = requests.get(url, headers=headers)
        snomed = (
            response.json()
            .get("useContext")[0]
            .get("valueCodeableConcept")
            .get("coding")[0]
            .get("code")
        )
        oid_to_conditions[oid] = snomed
        expansion = response.json().get("expansion").get("contains")
        for code in expansion:
            loinc = code.get("code")
            if loinc not in loinc_to_oids:
                loinc_to_oids[loinc] = []
            loinc_to_oids[loinc].append(oid)

    # deduplicate OIDs for each LOINC code
    for loinc in loinc_to_oids.keys():
        loinc_to_oids[loinc] = list(set(loinc_to_oids[loinc]))
    return oid_to_conditions, loinc_to_oids


def export_mapping_files(mapping: dict, filename: str):
    """
    Exports the mapping dictionary to a JSON file.
    :param mapping: Dictionary to save.
    :param filename: Output filename.
    """
    with open(filename, "w") as f:
        json.dump(mapping, f, indent=2)


if __name__ == "__main__":
    oids = get_ersd_valuesets(TES_ENDPOINTS)
    oid_to_conditions, loinc_to_oids = build_mapping_files(oids)
    export_mapping_files(oid_to_conditions, "data/accuracy_evaluation/oid_to_conditions.txt")
    export_mapping_files(loinc_to_oids, "data/accuracy_evaluation/loinc_to_oids.txt")
