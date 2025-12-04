import json
import os

import requests
from dotenv import load_dotenv

load_dotenv()

# sample run: python data/accuracy_evaluation/build_eval_files.py
# TES API Key can be obtained at https://tes.tools.aimsplatform.org/
TES_API_KEY = os.environ.get("TES_API_KEY")
TES_BASE_URL = "https://tes.tools.aimsplatform.org/api/fhir/ValueSet/"
headers = {"x-api-key": TES_API_KEY, "Accept": "application/fhir+json"}

# ERSD, key can be obtained at https://ersd.aimsplatform.org/#/api-keys
ERSD_API_KEY = os.environ.get("ERSD_API_KEY")
ERSD_BASE_URL = (
    f"https://ersd.aimsplatform.org/api/ersd/v3specification?format=json&api-key={ERSD_API_KEY}"
)

# Endpoints for LOINC-related value sets in TES and ERSD
VSTYPE_ENDPOINTS = ["lrtc", "lotc"]


def get_ersd_valuesets(endpoints: list) -> tuple[dict, list]:
    """
    Fetches LOINC value sets from ERSD API.
    :param endpoints: List of TES API endpoints to fetch value sets from.
    """
    response = requests.get(ERSD_BASE_URL)
    oids = []
    for item in response.json().get("entry"):
        if item["resource"].get("id") in endpoints:
            oid_list = [
                oid_url.split("/")[-1]
                for oid_url in item["resource"].get("compose").get("include")[0].get("valueSet")
            ]
            for oid in oid_list:
                if oid not in oids:
                    oids.append(oid)
    return response, oids


def get_tes_valuesets(endpoints: list) -> list:
    """
    Fetches LOINC value sets from TES API endpoints.
    :param endpoints: List of TES API endpoints to fetch value sets from.
    """
    oids = []
    for endpoint in endpoints:
        url = f"{TES_BASE_URL}{endpoint}"
        response = requests.get(url, headers=headers)
        for resp in response.json().get("compose").get("include"):
            oid = resp.get("valueSet")[0].split("/")[-1]
            if oid not in oids:
                oids.append(oid)
    return oids


def build_ersd_mapping_files(response: dict, oids: list) -> tuple[dict, dict]:
    """
    Builds mapping files for OIDs to conditions and LOINC codes to OIDs from ERSD response.
    :param response: ERSD API response containing value sets.
    :param oids: List of OIDs to build mappings for.
    """
    oid_to_conditions = {}
    loinc_to_oids = {}
    for entry in response.json().get("entry"):
        oid = entry.get("resource").get("id")
        if oid in oids:
            snomed = (
                entry.get("resource")
                .get("useContext")[0]
                .get("valueCodeableConcept")
                .get("coding")[0]
                .get("code")
            )
            oid_to_conditions[oid] = snomed
            expansion = entry.get("resource").get("expansion").get("contains")
            for code in expansion:
                loinc = code.get("code")
                if loinc not in loinc_to_oids:
                    loinc_to_oids[loinc] = []
                loinc_to_oids[loinc].append(oid)

    # deduplicate OIDs for each LOINC code
    for loinc in loinc_to_oids.keys():
        loinc_to_oids[loinc] = list(set(loinc_to_oids[loinc]))
    return oid_to_conditions, loinc_to_oids


def build_tes_mapping_files(oids: list) -> tuple[dict, dict]:
    """
    Builds mapping files for OIDs to conditions and LOINC codes to OIDs.
    TODO: Potentially refactor to build using rs-grouper
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


def evaluate_mapping_files(oid_to_conditions: dict, loinc_to_oids: dict):
    """
    Evaluates the mapping files for consistency.
    :param oid_to_conditions: OID to conditions mapping.
    :param loinc_to_oids: LOINC to OIDs mapping.
    """
    n = len(loinc_to_oids)
    print("Total LOINC codes mapped:", n)

    multiple_oids = {}
    for oids in loinc_to_oids.values():
        k = len(oids)
        multiple_oids[k] = multiple_oids.get(k, 0) + 1
    pct_multi_oids = (n - multiple_oids.get(1)) / n * 100
    print("LOINC codes mapped to multiple OIDs:", pct_multi_oids, "%")
    for k in sorted(multiple_oids):
        print(k, multiple_oids[k])

    multiple_conditions = {}
    for oids in loinc_to_oids.values():
        conditions = [oid_to_conditions.get(oid) for oid in oids]
        unique_count = len(set(conditions))
        multiple_conditions[unique_count] = multiple_conditions.get(unique_count, 0) + 1

    pct_multi_conditions = (n - multiple_conditions.get(1)) / n * 100
    print("LOINC codes mapped to multiple unique conditions:", pct_multi_conditions, "%")
    for k in sorted(multiple_conditions):
        print(k, multiple_conditions[k])


def export_mapping_files(mapping: dict, filename: str):
    """
    Exports the mapping dictionary to a JSON file.
    :param mapping: Dictionary to save.
    :param filename: Output filename.
    """
    with open(filename, "w") as f:
        json.dump(mapping, f, indent=2)


if __name__ == "__main__":
    # Build ERSD mapping files
    response, oids = get_ersd_valuesets(VSTYPE_ENDPOINTS)
    oid_to_conditions, loinc_to_oids = build_ersd_mapping_files(response, oids)

    # Build TES mapping files
    # tes_oids = get_tes_valuesets(VSTYPE_ENDPOINTS)
    # tes_oid_to_conditions, tes_loinc_to_oids = build_tes_mapping_files(tes_oids)

    evaluate_mapping_files(oid_to_conditions, loinc_to_oids)
    export_mapping_files(oid_to_conditions, "data/accuracy_evaluation/oid_to_conditions.txt")
    export_mapping_files(loinc_to_oids, "data/accuracy_evaluation/loinc_to_oids.txt")

    # evaluate_mapping_files(tes_oid_to_conditions, tes_loinc_to_oids)
    # export_mapping_files(tes_loinc_to_oids, "data/accuracy_evaluation/tes_loinc_to_oids.txt")
    # export_mapping_files(tes_oid_to_conditions, "data/accuracy_evaluation/tes_oid_to_conditions.txt")
