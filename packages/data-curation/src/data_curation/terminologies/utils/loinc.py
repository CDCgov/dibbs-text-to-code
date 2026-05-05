#!/usr/bin/env python"""

"""
data_curation.terminologies.utils.loinc
~~~~~~~~~~~~~~~~~~~~~~~~~

This module contains a number of helper functions designed to assist
with the process of extracting LOINC codes and their terms 
to generate and maintain embeddings in Opensearch for TTC.
"""
import csv
from datetime import datetime
import os
import requests
from .general import clean_text_string

# LOINC URLS
LOINC_BASE_URL = "https://loinc.regenstrief.org/searchapi/loincs?"
LOINC_LAB_ORDER_SUFFIX = "query=orderobs:Order+OR+orderobs:Both&rows=500"
LOINC_LAB_RESULT_SUFFIX = "query=orderobs:Observation+OR+orderobs:Both&rows=500"
LOINC_LAB_NAMES_SUFFIX = "query=orderobs:Order+OR+orderobs:Both+OR+orderobs:Observation&rows=500"
UMLS_LOINC_LAB_ATOMS_URL = "https://uts-ws.nlm.nih.gov/rest/content/2025AA/source/LNC/"
UMLS_LOINC_LAB_CROSSWALK_URL = "https://uts-ws.nlm.nih.gov/rest/crosswalk/current/source/LNC/"

# Get LOINC Username and Password
LOINC_USERNAME = os.environ.get("LOINC_USERNAME")
LOINC_PWD = os.environ.get("LOINC_PWD")

# LOINC Specific Files & Directories
LOINC_CS_NAMES = "./data/snoinc_extracts/loinc_other/consumer_names.csv"
LOINC_PARTS_ABBRV_SYNONYMS = "./data/snoinc_extracts/loinc_other/loinc_parts_abbrv_synonyms.txt"

# Data Filter Criteria
LOINC_TEXT_TO_FILTER = [
    "This term is intended to collate similar measurements for the LOINC SNOMED CT Collaboration"
]


def get_loinc_lab_names():  # noqa: D103
    api_url = LOINC_BASE_URL + LOINC_LAB_NAMES_SUFFIX
    loinc_vs_type = "Lab Names"
    all_loinc_rows = process_loinc_valueset(api_url, loinc_vs_type)

    # Now let's add the ConsumerName for each of the loinc codes
    all_loinc_rows = get_loinc_consumer_names(all_loinc_rows)
    return all_loinc_rows


def get_loinc_lab_orders():  # noqa: D103
    api_url = LOINC_BASE_URL + LOINC_LAB_ORDER_SUFFIX
    loinc_vs_type = "Lab Orders"
    loinc_order_rows = process_loinc_valueset(api_url, loinc_vs_type)
    # Now let's add the ConsumerName for each of the loinc codes
    loinc_order_rows = get_loinc_consumer_names(loinc_order_rows)

    return loinc_order_rows


def get_loinc_lab_results():  # noqa: D103
    api_url = LOINC_BASE_URL + LOINC_LAB_RESULT_SUFFIX
    loinc_vs_type = "Lab Results"
    loinc_result_rows = process_loinc_valueset(api_url, loinc_vs_type)
    # Now let's add the ConsumerName for each of the loinc codes
    loinc_result_rows = get_loinc_consumer_names(loinc_result_rows)
    return loinc_result_rows


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
    loinc_umls_urls = {}

    record_count = loinc_codes["ResponseSummary"]["RecordsFound"]
    print(f"{loinc_valueset_type} Record Count: {record_count}")
    current_row_count = loinc_codes["ResponseSummary"]["RowsReturned"]
    next_url_call = loinc_codes["ResponseSummary"]["Next"]

    while current_row_count > 0:
        if loinc_valueset_type not in ("UMLS Atoms"):
            loinc_rows = process_loinc_results(loinc_codes["Results"], loinc_rows)
        else:
            loinc_umls_urls = get_loinc_umls_urls(loinc_codes["Results"], loinc_umls_urls)

        if next_url_call is not None:
            next_loinc_response = requests.get(next_url_call, auth=(LOINC_USERNAME, LOINC_PWD))
            if next_loinc_response.status_code != 200:
                print(
                    f"ERROR Retrieving LOINC {loinc_valueset_type} CODES: {next_loinc_response.status_code}: {next_loinc_response.text}"
                )
                return
            loinc_codes = next_loinc_response.json()
            current_row_count = loinc_codes["ResponseSummary"]["RowsReturned"]
            next_url_call = loinc_codes.get("ResponseSummary").get("Next")
        else:
            current_row_count = 0

    if loinc_valueset_type not in ("UMLS Atoms"):
        return loinc_rows
    else:
        return loinc_umls_urls


def process_loinc_results(loinc_results, loinc_order_rows) -> dict:  # noqa: D103
    if len(loinc_results) == 0:
        print("NO RESULTS TO PROCESS!")
        return loinc_order_rows

    for loinc_result in loinc_results:
        loinc_order_rows = get_all_loinc_terms_per_code(loinc_result, loinc_order_rows)

    return loinc_order_rows


def get_loinc_umls_urls(loinc_results, loinc_rows_list):
    """
    This function will just generate and store the UMLS Urls that need
    to be used for each LOINC code.  They can be processed separately by another
    function.  Performance issues resulted in trying to do it all at once.
    """

    # loop through all the LOINC codes for labs (orders and results)
    for loinc_result in loinc_results:
        # get the LOINC Code and store it for use in the
        # UMLS urls
        loinc_code = loinc_result.get("LOINC_NUM")
        long_name = loinc_result.get("LONG_COMMON_NAME")
        loinc_umls_urls = {
            "atom": UMLS_LOINC_LAB_ATOMS_URL + loinc_code + "/atoms",
            "crs": UMLS_LOINC_LAB_CROSSWALK_URL + loinc_code,
            "long_name": long_name,
        }
        loinc_rows_list[loinc_code] = loinc_umls_urls

    return loinc_rows_list


def process_loincs_for_umls_urls() -> dict:
    loinc_api_url = LOINC_BASE_URL + LOINC_LAB_NAMES_SUFFIX
    umls_loinc_results = process_loinc_valueset(loinc_api_url, "UMLS Atoms")
    return umls_loinc_results


def get_all_loinc_terms_per_code(loinc_result: dict, loinc_order_rows) -> dict:  # noqa: D103
    result_row = {"code": loinc_result.get("LOINC_NUM")}
    # More human centered name for the concept
    result_row["display_name"] =clean_text_string(loinc_result.get("DisplayName"))
    # ';' separated list of related terms to the concept/code/term in question
    result_row["related_names"] = clean_text_string(loinc_result.get("RELATEDNAMES2"))

    # Paragraph of information concerning the concept/code/term in question
    defintion_desc = loinc_result.get("DefinitionDescription")
    if defintion_desc is not None:
        if not _filter_loinc_term(defintion_desc):
            result_row["definition_desc"] = clean_text_string(defintion_desc)
        else:
            result_row["definition_desc"] = ""
    result_row["lab_type"] = loinc_result.get("ORDER_OBS")
    # provides the fully specified name aka "Formal Name" in loinc
    result_row["full_name"] = clean_text_string(loinc_result.get("FormalName"))
    # let's get the 6 components of loinc lab tests
    result_row["property"] = clean_text_string(loinc_result.get("PROPERTY"))
    result_row["time_aspect"] = clean_text_string(loinc_result.get("TIME_ASPCT"))
    result_row["system"] = clean_text_string(loinc_result.get("SYSTEM"))
    result_row["scale_type"] = clean_text_string(loinc_result.get("SCALE_TYP"))
    result_row["method_type"] = clean_text_string(loinc_result.get("METHOD_TYP"))
    result_row["class_type"] = clean_text_string(loinc_result.get("CLASS"))
    result_row["short_name"] = clean_text_string(loinc_result.get("SHORTNAME"))
    result_row["long_name"] = clean_text_string(loinc_result.get("LONG_COMMON_NAME"))

    loinc_order_rows.append(result_row)

    return loinc_order_rows


def get_loinc_consumer_names(loinc_rows):
    cs_names = {}
    # loop through all the loinc rows and get the code
    # use that to look up the consumer name for each and add it to the row
    with open(LOINC_CS_NAMES, "r", encoding="utf-8") as file:
        reader = csv.DictReader(file, delimiter="|")
        for cs_row in reader:
            cs_code = cs_row.get("LoincNumber")
            cs_name = cs_row.get("ConsumerName")
            if cs_code and cs_name:
                cs_names[cs_code] = cs_name

    for row in loinc_rows:
        loinc_code = row.get("code")
        cs_name = cs_names.get(loinc_code)
        if cs_name:
            row["consumer_name"] = cs_name
    return loinc_rows


def _filter_loinc_term(text: str) -> bool:
    result: bool = False
    for filter_text in LOINC_TEXT_TO_FILTER:
        if filter_text in text:
            result = True
    return result