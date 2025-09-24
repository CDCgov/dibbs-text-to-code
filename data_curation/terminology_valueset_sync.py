#!/usr/bin/env python

"""This script provides the ability to pull down various medical terminology
valusets required for processing eICR data, specifically adding codes to
different data elements within an eICR message, such as Lab Order Name or
Lab Result Interpretation.

Current Available Valuesets:
    - Lab Names (Ordering & Resulting) - LOINC
    - Lab Orders - LOINC
    - Lab Observations - LOINC
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
import datetime
import json
import os
import sys

import requests
from dotenv import load_dotenv

load_dotenv()


# Set Terminology URLS
LOINC_BASE_URL = "https://loinc.regenstrief.org/searchapi/loincs?"
LOINC_LAB_ORDER_SUFFIX = "query=orderobs:Order+OR+orderobs:Both&rows=500"
LOINC_LAB_RESULT_SUFFIX = "query=orderobs:Observation+OR+orderobs:Both&rows=500"
LOINC_LAB_NAMES_SUFFIX = "query=orderobs:Order+OR+orderobs:Both+OR+orderobs:Observation&rows=500"
HL7_LAB_INTERP_URL = (
    "https://terminology.hl7.org/2.1.0/CodeSystem-v3-ObservationInterpretation.json"
)
UMLS_SNOMED_LAB_VALUES_URL = (
    "https://uts-ws.nlm.nih.gov/rest/content/current/source/SNOMEDCT_US/260245000/descendants"
)
UMLS_LOINC_CODE = ""
UMLS_LOINC_LAB_ATOMS_URL = "https://uts-ws.nlm.nih.gov/rest/content/2025AA/source/LNC/"
UMLS_LOINC_LAB_CROSSWALK_URL = "https://uts-ws.nlm.nih.gov/rest/crosswalk/current/source/LNC/"

# Get Terminology Usernames and Passwords
LOINC_USERNAME = os.environ.get("LOINC_USERNAME")
LOINC_PWD = os.environ.get("LOINC_PWD")
UMLS_API_KEY = os.environ.get("UMLS_API_KEY")

# File settings
CSV_DIRECTORY = "../data/snoinc_extracts"
TMP_DIRECTORY = "./tmp"

# Data Filter Criteria
LOINC_TEXT_TO_FILTER = [
    "This term is intended to collate similar measurements for the LOINC SNOMED CT Collaboration"
]


def get_umls_snomed_lab_values():  # noqa: D103
    if UMLS_API_KEY is None:
        raise KeyError("UMLS_API_KEY Environment Variable must be set to a proper UMLS API Key!")
    snomed_filename = f"snomed_lab_value_{datetime.datetime.now().strftime('%Y%m%d')}.csv"
    page_num = 1
    page_size = 500
    params = {"apiKey": UMLS_API_KEY, "pageNumber": page_num, "pageSize": page_size}
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
        params = {"apiKey": UMLS_API_KEY, "pageNumber": page_num, "pageSize": page_size}
        umls_response = requests.get(UMLS_SNOMED_LAB_VALUES_URL, params=params)

    print(f"{snomed_row_count} Codes Extracted")
    save_valueset_csv_file(snomed_filename, snomed_rows)


def get_hl7_lab_interp():  # noqa: D103
    hl7_filename = f"hl7_lab_interp_{datetime.datetime.now().strftime('%Y%m%d')}.csv"
    hl7_response = requests.get(HL7_LAB_INTERP_URL)
    hl7_rows = []

    if hl7_response.status_code != 200:
        print(
            f"ERROR Retrieving HL7 LAB Interpretation CODES: {hl7_response.status_code}: {hl7_response.text}",
            file=sys.stderr,
        )
        sys.exit(1)
    hl7_codes = hl7_response.json().get("concept")

    if hl7_codes is not None:
        record_count = len(hl7_codes)
        print(f"HL7 Lab Interpretation Record Count: {record_count}")

        for hl7_row in hl7_codes:
            hl7_code = hl7_row.get("code")
            hl7_text = hl7_row.get("display")
            # NOTE: we can add back in the definition as description, but there are some
            # special character filtering we may need to do and some of the
            # data in this field could clutter things up
            # hl7_desc = hl7_row.get("definition")
            if (
                hl7_code
                and not hl7_code.startswith(("_", "Observation", "OBX", "ReactivityObs"))
                and hl7_text
            ):
                result_row = {"code": hl7_code, "text": hl7_text}
                hl7_rows.append(result_row)
        save_valueset_csv_file(hl7_filename, hl7_rows)


def get_loinc_lab_names():  # noqa: D103
    api_url = LOINC_BASE_URL + LOINC_LAB_NAMES_SUFFIX
    loinc_filename = f"loinc_lab_names_{datetime.datetime.now().strftime('%Y%m%d')}.csv"
    loinc_vs_type = "Lab Names"
    loinc_order_rows = process_loinc_valueset(api_url, loinc_vs_type)

    save_valueset_csv_file(loinc_filename, loinc_order_rows)


def get_loinc_lab_orders():  # noqa: D103
    api_url = LOINC_BASE_URL + LOINC_LAB_ORDER_SUFFIX
    loinc_filename = f"loinc_lab_orders_{datetime.datetime.now().strftime('%Y%m%d')}.csv"
    loinc_vs_type = "Lab Orders"
    loinc_order_rows = process_loinc_valueset(api_url, loinc_vs_type)

    save_valueset_csv_file(loinc_filename, loinc_order_rows)


def get_loinc_lab_results():  # noqa: D103
    api_url = LOINC_BASE_URL + LOINC_LAB_RESULT_SUFFIX
    loinc_filename = f"loinc_lab_result_{datetime.datetime.now().strftime('%Y%m%d')}.csv"
    loinc_vs_type = "Lab Results"
    loinc_result_rows = process_loinc_valueset(api_url, loinc_vs_type)

    save_valueset_csv_file(loinc_filename, loinc_result_rows)


def get_loinc_umls_related_results():  # noqa: D103
    if UMLS_API_KEY is None:
        raise KeyError("UMLS_API_KEY Environment Variable must be set to a proper UMLS API Key!")
    loinc_api_url = LOINC_BASE_URL + LOINC_LAB_NAMES_SUFFIX
    url_filename = "loinc_umls_related_names_urls.json"
    umls_filename = f"loinc_umls_related_names_{datetime.datetime.now().strftime('%Y%m%d')}.csv"
    umls_loinc_results = process_loinc_valueset(loinc_api_url, "UMLS Atoms")

    print(f"LOINC RELATED NAMES URLS ADDED: {len(umls_loinc_results)}")

    save_url_file(url_filename, umls_loinc_results)

    umls_rows = process_loinc_codes_with_umls(url_filename)
    print(f"LOINC UMLS Related Names Rows: {len(umls_rows)}")
    save_valueset_csv_file(umls_filename, umls_rows)


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

    if len(loinc_rows) > 0:
        return loinc_rows
    else:
        return loinc_umls_urls


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
        loinc_umls_urls = {
            "atom": UMLS_LOINC_LAB_ATOMS_URL + loinc_code + "/atoms",
            "crs": UMLS_LOINC_LAB_CROSSWALK_URL + loinc_code,
        }
        loinc_rows_list[loinc_code] = loinc_umls_urls

    return loinc_rows_list


def process_loinc_codes_with_umls(filename: str) -> dict:  # noqa: D103
    if UMLS_API_KEY is None:
        raise KeyError("UMLS_API_KEY Environment Variable must be set to a proper UMLS API Key!")

    if not os.path.exists(TMP_DIRECTORY):
        raise KeyError("Directory where file is expected is missing!")

    try:
        full_file_path = os.path.join(TMP_DIRECTORY, filename)

        with open(full_file_path, "r") as file:
            umls_urls = json.load(file)
    except FileNotFoundError:
        print(f"Error: {full_file_path} not found. Please ensure the file exists.")
    except json.JSONDecodeError:
        print(f"Error: Invalid JSON format in {full_file_path}.")

    print("Processing UMLS URLS for LOINC Codes!")
    umls_loinc_rows = []
    loinc_code_count = 0

    # loop through all the LOINC codes in dict along
    # with all the correlated umls urls
    for loinc_code, urls_dict in umls_urls.items():
        umls_atom_url = urls_dict["atom"]
        umls_crs_url = urls_dict["crs"]
        loinc_code_count += 1

        print(f"CODE: {loinc_code_count}")
        print(f"ROW COUNTS: {len(umls_loinc_rows)}")

        ###########################################################################
        # LOINC ATOMIC TERMS PROCESSING
        ###########################################################################
        atom_page_num = 1
        page_size = 500
        lang = "ENG"
        params = {
            "apiKey": UMLS_API_KEY,
            "pageNumber": atom_page_num,
            "pageSize": page_size,
            "language": lang,
        }

        umls_atom_response = requests.get(umls_atom_url, params=params)
        atom_row_count = 0

        while umls_atom_response.status_code == 200:
            # NOTE: the UMLS responses are a bit slow
            #  you can use the print statement below to get a
            #  better idea of the progress if needed.
            # print(f"Processing LOINC ATOM page {atom_page_num}")
            umls_atom_results = umls_atom_response.json().get("result")

            for atom_result in umls_atom_results:
                related_name = atom_result.get("name")
                if related_name:
                    atom_row = {"code": loinc_code, "text": related_name}
                    umls_loinc_rows.append(atom_row)
                    atom_row_count += 1

            atom_page_num += 1
            params = {
                "apiKey": UMLS_API_KEY,
                "pageNumber": atom_page_num,
                "pageSize": page_size,
                "language": lang,
            }

            umls_atom_response = requests.get(umls_atom_url, params=params)

        ###########################################################################
        # LOINC CROSSWALK TERMS PROCESSING
        ###########################################################################
        crs_page_num = 1
        page_size = 500
        lang = "ENG"
        params = {
            "apiKey": UMLS_API_KEY,
            "pageNumber": crs_page_num,
            "pageSize": page_size,
            "language": lang,
        }
        umls_crs_response = requests.get(umls_crs_url, params=params)
        crs_row_count = 0
        max_page = 1

        while umls_crs_response.status_code == 200 and crs_page_num <= max_page:
            max_page = umls_crs_response.json().get("pageCount")
            # NOTE: the UMLS responses are a bit slow
            #  you can use the print statement below to get a
            #  better idea of the progress if needed.
            # print(f"Processing LOINC CROSSWALK page {crs_page_num}")
            umls_crs_results = umls_crs_response.json().get("result")

            for crs_result in umls_crs_results:
                related_name = crs_result.get("name")
                root_source = crs_result.get("rootSource")
                if "LNC-" not in root_source and related_name:
                    crs_row = {"code": loinc_code, "text": related_name}
                    umls_loinc_rows.append(crs_row)
                    crs_row_count += 1

            crs_page_num += 1
            params = {
                "apiKey": UMLS_API_KEY,
                "pageNumber": crs_page_num,
                "pageSize": page_size,
                "language": lang,
            }

            umls_crs_response = requests.get(umls_crs_url, params=params)

    return umls_loinc_rows


def process_loinc_results(loinc_results, loinc_order_rows) -> dict:  # noqa: D103
    if len(loinc_results) == 0:
        print("NO RESULTS TO PROCESS!")
        return loinc_order_rows

    for loinc_result in loinc_results:
        loinc_order_rows = get_all_loinc_terms_per_code(loinc_result, loinc_order_rows)

    return loinc_order_rows


def get_all_loinc_terms_per_code(loinc_result: dict, loinc_order_rows) -> dict:  # noqa: D103
    result_code = loinc_result.get("LOINC_NUM")
    result_row = {"code": result_code}
    short_name = loinc_result.get("SHORTNAME")
    long_name = loinc_result.get("LONG_COMMON_NAME")
    display_name = loinc_result.get("DisplayName")
    related_names = loinc_result.get("RELATEDNAMES2")
    defintion_desc = loinc_result.get("DefinitionDescription")

    if short_name is not None:
        result_row["short_name"] = short_name
    if long_name is not None:
        result_row["long_name"] = long_name

    # Adding additional fields to extract terms from to help supplement
    # data for learning in our models
    # NOTE: We can change/remove these additional fields later or even
    #  make them configurable

    # More human centered name for the concept
    if display_name is not None:
        result_row["display_name"] = display_name
    # Paragraph of information concerning the concept/code/term in question
    if defintion_desc is not None and not _filter_loinc_term(defintion_desc):
        result_row["definition_desc"] = loinc_result.get("DefinitionDescription")
    # ';' separated list of related terms to the concept/code/term in question
    if related_names is not None:
        result_row["related_names"] = related_names

    loinc_order_rows.append(result_row)

    return loinc_order_rows


def save_valueset_csv_file(filename: str, contents: dict):  # noqa: D103
    if not filename.strip():
        print("No filename supplied.  Failed to save CSV file!")
        return

    if contents is None and len(contents) == 0:
        print("Empty file contents!  Failed to save CSV!")
        return

    if not os.path.exists(CSV_DIRECTORY):
        os.makedirs(CSV_DIRECTORY)

    try:
        full_file_path = os.path.join(CSV_DIRECTORY, filename)
        csv_headers = contents[0].keys()

        with open(full_file_path, "w", newline="", encoding="utf-8") as csvfile:
            writer = csv.DictWriter(csvfile, csv_headers, delimiter="|")
            writer.writeheader()
            writer.writerows(contents)
        print(f"CSV File successfully saved as {full_file_path}")

    except ValueError as e:
        print(f"Error parsing Dict Contents: {e}")
    except Exception as e:
        print(f"An error occured: {e}")


def save_loinc_part_dict_file(filename: str, contents: dict):  # noqa: D103
    if not filename.strip():
        print("No filename supplied.  Failed to save LOINC Part Dictionary!")
        return

    if contents is None and len(contents) == 0:
        print("Empty file contents!  Failed to save LOINC Part Dictionary!")
        return

    if not os.path.exists(CSV_DIRECTORY):
        os.makedirs(CSV_DIRECTORY)

    try:
        full_file_path = os.path.join(CSV_DIRECTORY, filename)

        with open(full_file_path, "w", encoding="utf-8") as dictfile:
            json.dump(contents, dictfile, indent=4)
        print(f"JSON Dictionary for Loinc Part saved successfully as: {full_file_path}")

    except ValueError as e:
        print(f"Error parsing Dict Contents: {e}")
    except Exception as e:
        print(f"An error occured: {e}")


def save_url_file(filename: str, contents: dict):  # noqa: D103
    if not filename.strip():
        print("No filename supplied.  Failed to save URL File!")
        return

    if contents is None and len(contents) == 0:
        print("Empty file contents!  Failed to save URL File!")
        return

    if not os.path.exists(TMP_DIRECTORY):
        os.makedirs(TMP_DIRECTORY)

    try:
        full_file_path = os.path.join(TMP_DIRECTORY, filename)

        with open(full_file_path, "w", encoding="utf-8") as dictfile:
            json.dump(contents, dictfile, indent=4)
        print(f"URL File successfully saved as: {full_file_path}")

    except ValueError as e:
        print(f"Error parsing Dict Contents: {e}")
    except Exception as e:
        print(f"An error occured: {e}")


def _get_loinc_abbrv_syns(
    part_code: str,
    part_name: str,
    repl_name: str,
    pref_abrv: str,
    synonym: str,
    loinc_row: dict,
) -> dict:
    filter_from_names = ["", "$"]

    if loinc_row.get("code") == part_code:
        if (
            repl_name is not None
            and repl_name not in filter_from_names
            and repl_name != part_name
            and repl_name not in loinc_row.get("synonyms")
        ):
            loinc_row["synonyms"].append(repl_name)
        if (
            pref_abrv is not None
            and pref_abrv not in filter_from_names
            and pref_abrv != part_name
            and pref_abrv not in loinc_row.get("synonyms")
            and pref_abrv not in loinc_row.get("abbrv")
        ):
            loinc_row["abbrv"].append(pref_abrv)

        if (
            synonym is not None
            and synonym not in filter_from_names
            and synonym != part_name
            and synonym not in loinc_row.get("synonyms")
            and synonym not in loinc_row.get("abbrv")
        ):
            loinc_row["synonyms"].append(synonym)
    return loinc_row


def create_loinc_part_abbrv_syn_dicts():
    """
    Creates single file dictionary for each of the different
    LOINC parts, which contains each LOINC Part Code, Name
    and Abbreviations and Synonyms
    """
    file_path = "./loinc/LOINC_PARTS_ABBRV_SYNONYMS.txt"

    # Separate LOINC Part Dictionaries
    component_dict = {}
    method_dict = {}
    property_dict = {}
    scale_dict = {}
    system_dict = {}
    time_dict = {}
    component_file = f"loinc_component_abbrv_syn_{datetime.datetime.now().strftime('%Y%m%d')}.json"
    method_file = f"loinc_method_abbrv_syn_{datetime.datetime.now().strftime('%Y%m%d')}.json"
    property_file = f"loinc_property_abbrv_syn_{datetime.datetime.now().strftime('%Y%m%d')}.json"
    scale_file = f"loinc_scale_abbrv_syn_{datetime.datetime.now().strftime('%Y%m%d')}.json"
    system_file = f"loinc_system_abbrv_syn_{datetime.datetime.now().strftime('%Y%m%d')}.json"
    time_file = f"loinc_time_abbrv_syn_{datetime.datetime.now().strftime('%Y%m%d')}.json"

    row_count = 1

    with open(file_path, "r", encoding="utf-8") as file:
        reader = csv.DictReader(file, delimiter="|")
        for row in reader:
            # NOTE: the below print statement can be used
            # to track down errors within the access extract file
            # for particular rows with character issues
            # print(f"ROW_COUNT: {row_count}")
            row_count = row_count + 1
            part_code = row.get("PART_NUM")
            axis_name = row.get("PART_TYPE_NAME_NAME")
            part_name = row.get("PART")
            repl_name = row.get("PART_NAME")
            pref_abrv = row.get("PREF_ABRV")
            synonym = row.get("SYNONYM")

            # build various LOINC Part dicts
            if axis_name == "COMPONENT":
                existing_row = component_dict.get(part_name)
                if not existing_row:
                    existing_row = {"code": part_code, "abbrv": [], "synonyms": []}
                    component_dict[part_name] = existing_row
                existing_row = _get_loinc_abbrv_syns(
                    part_code, part_name, repl_name, pref_abrv, synonym, existing_row
                )
            elif axis_name == "METHOD":
                existing_row = method_dict.get(part_name)
                if not existing_row:
                    existing_row = {"code": part_code, "abbrv": [], "synonyms": []}
                    method_dict[part_name] = existing_row
                existing_row = _get_loinc_abbrv_syns(
                    part_code, part_name, repl_name, pref_abrv, synonym, existing_row
                )
            elif axis_name == "PROPERTY":
                existing_row = property_dict.get(part_name)
                if not existing_row:
                    existing_row = {"code": part_code, "abbrv": [], "synonyms": []}
                    property_dict[part_name] = existing_row
                existing_row = _get_loinc_abbrv_syns(
                    part_code, part_name, repl_name, pref_abrv, synonym, existing_row
                )
            elif axis_name == "SYSTEM":
                existing_row = system_dict.get(part_name)
                if not existing_row:
                    existing_row = {"code": part_code, "abbrv": [], "synonyms": []}
                    system_dict[part_name] = existing_row
                existing_row = _get_loinc_abbrv_syns(
                    part_code, part_name, repl_name, pref_abrv, synonym, existing_row
                )
            elif axis_name == "TIME":
                existing_row = time_dict.get(part_name)
                if not existing_row:
                    existing_row = {"code": part_code, "abbrv": [], "synonyms": []}
                    time_dict[part_name] = existing_row
                existing_row = _get_loinc_abbrv_syns(
                    part_code, part_name, repl_name, pref_abrv, synonym, existing_row
                )
            elif axis_name == "SCALE":
                existing_row = scale_dict.get(part_name)
                if not existing_row:
                    existing_row = {"code": part_code, "abbrv": [], "synonyms": []}
                    scale_dict[part_name] = existing_row
                existing_row = _get_loinc_abbrv_syns(
                    part_code, part_name, repl_name, pref_abrv, synonym, existing_row
                )
    print(f"Total Rows Processed: {row_count}")
    # write each dict out into it's own file
    save_loinc_part_dict_file(component_file, component_dict)
    save_loinc_part_dict_file(method_file, method_dict)
    save_loinc_part_dict_file(property_file, property_dict)
    save_loinc_part_dict_file(system_file, system_dict)
    save_loinc_part_dict_file(time_file, time_dict)
    save_loinc_part_dict_file(scale_file, scale_dict)


def _filter_loinc_term(text: str) -> bool:
    result: bool = False
    for filter_text in LOINC_TEXT_TO_FILTER:
        if filter_text in text:
            result = True
    return result


def main(  # noqa: D103
    all_vs: bool,
    lab_orders: bool,
    lab_obs: bool,
    lab_values: bool,
    lab_interp: bool,
    lab_names: bool,
    loinc_abbr_syn: bool,
    loinc_umls_syn: bool,
):  # noqa: D103
    print("Starting Terminology ValueSet Sync...")
    if all_vs or lab_orders:
        print("Getting LOINC Lab Orders...")
        get_loinc_lab_orders()
    if all_vs or lab_obs:
        print("Getting LOINC Lab Observations...")
        get_loinc_lab_results()
    if all_vs or lab_values:
        print("Getting SNOMED Lab Result Values...")
        get_umls_snomed_lab_values()
    if all_vs or lab_interp:
        print("Getting HL7 Lab Result Interpretations...")
        get_hl7_lab_interp()
    if all_vs or lab_names:
        print("Getting LOINC Lab Names...")
        get_loinc_lab_names()
    if all_vs or loinc_abbr_syn:
        print("Getting LOINC Part Abreviations & Synonyms...")
        create_loinc_part_abbrv_syn_dicts()
    if all_vs or loinc_umls_syn:
        print("Getting LOINC UMLS Related Names...")
        get_loinc_umls_related_results()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="A script to pull down various Medical Terminology Value Set Codes and Texts, specify which sets."
    )
    parser.add_argument(
        "--lab_names",
        action="store_true",
        help="For ALL Loinc Lab Names both Ordering & Resulting",
    )
    parser.add_argument("--lab_orders", action="store_true", help="For Loinc Lab Orders")
    parser.add_argument("--lab_obs", action="store_true", help="For Loinc Lab Observations")
    parser.add_argument("--lab_values", action="store_true", help="For Snomed Lab Result Values")
    parser.add_argument("--lab_interp", action="store_true", help="For HL7 Lab Interpretations")
    parser.add_argument("--all", action="store_true", help="If present, pulls all value sets")
    parser.add_argument(
        "--loinc_abbr_syn",
        action="store_true",
        help="For Loinc Part Abreviations and Synonyms",
    )
    parser.add_argument(
        "--loinc_umls_syn",
        action="store_true",
        help="For Loinc UMLS Related Names (Atomic & Crosswalk)",
    )

    args = parser.parse_args()
    main(
        args.all,
        args.lab_orders,
        args.lab_obs,
        args.lab_values,
        args.lab_interp,
        args.lab_names,
        args.loinc_abbr_syn,
        args.loinc_umls_syn,
    )
