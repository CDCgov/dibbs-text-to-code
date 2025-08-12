#!/usr/bin/env python

"""This script provides the ability to pull down various medical terminology
valusets required for processing eICR data, specifically adding codes to
different data elements within an eICR message, such as Lab Order Name or
Lab Result Interpretation.

Current Available Valuesets:
    - Lab Orders (Lab Name (Ordering)) - LOINC
    - Lab Observations (Lab Name (Resulting)) - LOINC
    - Lab Result Value - SNOMED
    - Lab Result Interpretation - HL7 Observation Interpretations

Requirements:
    - SNOMED - requires an UMLS API KEY stored in an environment variable:
        - UMLS_API_KEY
    - LOINC - requires a LOINC username and password stored in environment variables:
        - LOINC_USERNAME
        - LOINC_PWD
"""

import argparse
import csv
import os
import sys

import requests

# Set Terminology URLS
LOINC_BASE_URL = "https://loinc.regenstrief.org/searchapi/loincs?"
LOINC_LAB_ORDER_SUFFIX = "query=orderobs:Order+OR+orderobs:Both&rows=500"
LOINC_LAB_RESULT_SUFFIX = "query=orderobs:Observation+OR+orderobs:Both&rows=500"
HL7_LAB_INTERP_URL = (
    "https://www.fhir.org/guides/stats2/valueset-us.nlm.vsac-2.16.840.1.113883.1.11.78.json"
)
UMLS_SNOMED_LAB_VALUES_URL = (
    "https://uts-ws.nlm.nih.gov/rest/content/current/source/SNOMEDCT_US/260245000/descendants"
)

# Get Terminology Usernames and Passwords
LOINC_USERNAME = os.environ.get("LOINC_USERNAME")
LOINC_PWD = os.environ.get("LOINC_PWD")
UMLS_API_KEY = os.environ.get("UMLS_API_KEY")

# CSV file settings
CSV_DIRECTORY = "tmp/"


def get_umls_snomed_lab_values():  # noqa: D103
    if UMLS_API_KEY is None:
        raise KeyError("UMLS_API_KEY Environment Variable must be set to a proper UMLS API Key!")
    snomed_filename = "snomed_lab_value.csv"
    page_num = 1
    params = {"apiKey": UMLS_API_KEY, "pageNumber": page_num}
    umls_response = requests.get(UMLS_SNOMED_LAB_VALUES_URL, params=params)
    snomed_row_count = 0
    snomed_rows = []

    while umls_response.status_code == 200:
        # NOTE: the UMLS responses are a bit slow
        #  you can use the print statement below to get a
        #  better idea of the progress if needed.
        # print(f"Processing SNOMED page {page_num}")
        umls_results = umls_response.json().get("result")

        for result in umls_results:
            snomed_code = result.get("ui")
            snomed_text = result.get("name")
            if snomed_code and snomed_text:
                result_row = {"code": snomed_code, "text": snomed_text}
                snomed_rows.append(result_row)
                snomed_row_count += 1

        page_num += 1
        params = {"apiKey": UMLS_API_KEY, "pageNumber": page_num}
        umls_response = requests.get(UMLS_SNOMED_LAB_VALUES_URL, params=params)

    print(f"{snomed_row_count} Codes Extracted")
    save_valueset_csv_file(snomed_filename, snomed_rows)


def get_hl7_lab_interp():  # noqa: D103
    hl7_filename = "hl7_lab_interp.csv"
    hl7_response = requests.get(HL7_LAB_INTERP_URL)

    if hl7_response.status_code != 200:
        print(
            f"ERROR Retrieving HL7 LAB Interpretation CODES: {hl7_response.status_code}: {hl7_response.text}",
            file=sys.stderr,
        )
        sys.exit(1)
    hl7_codes = hl7_response.json().get("compose").get("include")[0].get("concept")

    if hl7_codes is not None:
        record_count = hl7_response.json().get("expansion").get("total")
        print(f"HL7 Lab Interpretation Record Count: {record_count}")

        # replace 'display' key with 'text
        key_replacements = {"display": "text"}
        for hl7_row in hl7_codes:
            for old_key, new_key in key_replacements.items():
                if old_key in hl7_row:
                    hl7_row[new_key] = hl7_row[old_key]
                    del hl7_row[old_key]
        save_valueset_csv_file(hl7_filename, hl7_codes)


def get_loinc_lab_orders():  # noqa: D103
    api_url = LOINC_BASE_URL + LOINC_LAB_ORDER_SUFFIX
    loinc_filename = "loinc_lab_orders.csv"
    loinc_vs_type = "Lab Orders"
    loinc_order_rows = process_loinc_valueset(api_url, loinc_vs_type)

    save_valueset_csv_file(loinc_filename, loinc_order_rows)


def get_loinc_lab_results():  # noqa: D103
    api_url = LOINC_BASE_URL + LOINC_LAB_RESULT_SUFFIX
    loinc_filename = "loinc_lab_result.csv"
    loinc_vs_type = "Lab Results"
    loinc_result_rows = process_loinc_valueset(api_url, loinc_vs_type)

    save_valueset_csv_file(loinc_filename, loinc_result_rows)


def process_loinc_valueset(api_url, loinc_valueset_type):  # noqa: D103
    if LOINC_USERNAME is None or LOINC_PWD is None:
        raise KeyError(
            "LOINC_USERNAME and LOINC_PWD environment variables are required to pull from LOINC!"
        )
    loinc_response = requests.get(api_url, auth=(LOINC_USERNAME, LOINC_PWD))
    if loinc_response.status_code != 200:
        print(
            f"ERROR Retrieving LOINC {loinc_valueset_type} CODES: {loinc_response.status_code}: {loinc_response.text}"
        )
        return None

    loinc_codes = loinc_response.json()
    loinc_rows = []

    record_count = loinc_codes["ResponseSummary"]["RecordsFound"]
    print(f"{loinc_valueset_type} Record Count: {record_count}")
    current_row_count = loinc_codes["ResponseSummary"]["RowsReturned"]
    next_url_call = loinc_codes["ResponseSummary"]["Next"]

    while current_row_count > 0 or next_url_call is None:
        loinc_rows = process_loinc_results(loinc_codes["Results"], loinc_rows)

        next_loinc_response = requests.get(next_url_call, auth=(LOINC_USERNAME, LOINC_PWD))
        if next_loinc_response.status_code != 200:
            print(
                f"ERROR Retrieving LOINC {loinc_valueset_type} CODES: {next_loinc_response.status_code}: {next_loinc_response.text}"
            )
            return
        loinc_codes = next_loinc_response.json()
        current_row_count = loinc_codes["ResponseSummary"]["RowsReturned"]
        next_url_call = loinc_codes.get("ResponseSummary").get("Next")
        if next_url_call is None:
            break

    return loinc_rows


def process_loinc_results(loinc_results, loinc_order_rows) -> dict:  # noqa: D103
    if len(loinc_results) == 0:
        print("NO RESULTS TO PROCESS!")
        return loinc_order_rows

    for loinc_result in loinc_results:
        loinc_order_rows = get_all_loinc_terms_per_code(loinc_result, loinc_order_rows)

    return loinc_order_rows


def get_all_loinc_terms_per_code(loinc_result: dict, loinc_order_rows) -> dict:  # noqa: D103
    result_code = loinc_result.get("LOINC_NUM")
    if loinc_result.get("SHORTNAME") is not None:
        result_row = {"code": result_code, "text": loinc_result.get("SHORTNAME")}
        loinc_order_rows.append(result_row)
    if loinc_result.get("LONG_COMMON_NAME") is not None:
        result_row = {"code": result_code, "text": loinc_result.get("LONG_COMMON_NAME")}
        loinc_order_rows.append(result_row)

    # NOTE: There are other fields that have additional descriptions that we can pull
    #  from as well.  ie. TermDescriptions [], FormalName, and DisplayName.
    #  Will leave these out for now.

    return loinc_order_rows


def save_valueset_csv_file(filename: str, contents: dict):  # noqa: D103
    if not filename.strip():
        print("No filename supplied.  Failed to save CSV file!")
        return

    if contents is None and len(contents) == 0:
        print("Empty file contents!  Failed to save CSV!")
        return

    try:
        full_file_path = os.path.join(CSV_DIRECTORY, filename)
        csv_headers = contents[0].keys()

        with open(full_file_path, "w", newline="", encoding="utf-8") as csvfile:
            writer = csv.DictWriter(csvfile, csv_headers)
            writer.writeheader()
            writer.writerows(contents)
        print(f"CSV File successfully saved as {full_file_path}")

    except ValueError as e:
        print(f"Error parsing Dict Contents: {e}")
    except Exception as e:
        print(f"An error occured: {e}")


def main(all_vs: bool, lab_orders: bool, lab_obs: bool, lab_values: bool, lab_interp: bool):  # noqa: D103
    if all_vs or lab_orders:
        get_loinc_lab_orders()
    if all_vs or lab_obs:
        get_loinc_lab_results()
    if all_vs or lab_values:
        get_umls_snomed_lab_values()
    if all_vs or lab_interp:
        get_hl7_lab_interp()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="A script to pull down various Medical Terminology Value Set Codes and Texts, specify which sets."
    )
    parser.add_argument("--lab_orders", action="store_true", help="For Loinc Lab Orders")
    parser.add_argument("--lab_obs", action="store_true", help="For Loinc Lab Observations")
    parser.add_argument("--lab_values", action="store_true", help="For Snomed Lab Result Values")
    parser.add_argument("--lab_interp", action="store_true", help="For HL7 Lab Interpretations")
    parser.add_argument("--all", action="store_true", help="If present, pulls all value sets")

    args = parser.parse_args()
    main(args.all, args.lab_orders, args.lab_obs, args.lab_values, args.lab_interp)
