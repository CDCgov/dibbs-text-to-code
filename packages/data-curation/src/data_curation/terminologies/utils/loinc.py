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
import json
import os
from pathlib import Path
import requests
from .general import clean_text_string

# LOINC URLS
LOINC_BASE_URL = "https://loinc.regenstrief.org/searchapi/loincs?"
LOINC_LAB_ORDER_QUERY = "orderobs:Order+OR+orderobs:Both&rows=500"
LOINC_LAB_RESULT_QUERY = "orderobs:Observation+OR+orderobs:Both&rows=500"
LOINC_LAB_NAMES_QUERY = "orderobs:Order+OR+orderobs:Both+OR+orderobs:Observation&rows=500"
UMLS_LOINC_LAB_ATOMS_URL = "https://uts-ws.nlm.nih.gov/rest/content/2025AA/source/LNC/"
UMLS_LOINC_LAB_CROSSWALK_URL = "https://uts-ws.nlm.nih.gov/rest/crosswalk/current/source/LNC/"
LOINC_META_URL = "https://loinc.regenstrief.org/api/v1/Loinc"

# Get LOINC Username and Password
LOINC_USERNAME = os.environ.get("LOINC_USERNAME")
LOINC_PWD = os.environ.get("LOINC_PWD")

# LOINC Specific Files & Directories
BASE_FOLDER = Path(__file__).resolve().parent[4] / "data" / "snoinc_extracts"
LOINC_CS_NAMES = BASE_FOLDER / "loinc_other"/ "consumer_names.csv"
LOINC_PARTS_ABBRV_SYNONYMS = BASE_FOLDER / "loinc_other"/ "loinc_parts_abbrv_synonyms.txt"
LAB_NAMES = "loinc_lab_names"
LAB_ORDERS = "loinc_lab_orders"
LAB_RESULT = "loinc_lab_result"

# Data Filter Criteria
LOINC_TEXT_TO_FILTER = [
    "This term is intended to collate similar measurements for the LOINC SNOMED CT Collaboration"
]


def get_loinc_lab_names(version: str = ""):
    """Process to get the all, or version specific, LOINC Codes and terms
        via the LOINC API for all labs (Lab Names) that are categorized as
        'Observations', 'Orders', or 'Both'.

        :param version: Text string of the version number you want to 
            use to filter LOINC codes for.

        :returns: A list of dictionaries containing LOINC lab name records
            including codes, terms, and axis information.
    """
    # if version is supplied we grab the delta 
    # and filter based upon version changes
    # otherwise grab all Orders/Obsersavtions/Both
    if version != "":
        api_url = LOINC_BASE_URL + f"query=versionlastchanged:{version}+AND+" + LOINC_LAB_NAMES_QUERY
    else:
        api_url = LOINC_BASE_URL + f"query={LOINC_LAB_NAMES_QUERY}" 
    loinc_vs_type = "Lab Names"
    all_loinc_rows = process_loinc_valueset(api_url, loinc_vs_type)

    # Now let's add the ConsumerName for each of the loinc codes
    all_loinc_rows = get_loinc_consumer_names(all_loinc_rows)
    return all_loinc_rows


def get_loinc_lab_orders(version: str = ""):
    """Process to get all of the, or version specific, LOINC Codes and terms
        via the LOINC API for all lab 'Orders' that are categorized as 
        'Orders', or 'Both'.

        :param version: Text string of the version number you want to 
            use to filter LOINC codes for.

        :returns: A list of dictionaries containing LOINC lab order records
            including codes, terms, and axis information.
    """
    # if version is supplied we grab the delta 
    # and filter based upon version changes
    # otherwise grab all Orders
    if version != "":
        api_url = LOINC_BASE_URL + f"query=versionlastchanged:{version}+AND+" + LOINC_LAB_ORDER_QUERY
    else:
        api_url = LOINC_BASE_URL + f"query={LOINC_LAB_ORDER_QUERY}"
    loinc_vs_type = "Lab Orders"
    loinc_order_rows = process_loinc_valueset(api_url, loinc_vs_type)
    # Now let's add the ConsumerName for each of the loinc codes
    loinc_order_rows = get_loinc_consumer_names(loinc_order_rows)

    return loinc_order_rows


def get_loinc_lab_results(version: str = ""):
    """Process to get all of the, or version specific, LOINC Codes and terms
        via the LOINC API for all lab 'Observations' (Lab Results) that are
        categorized as 'Observations', or 'Both'.

        :param version: Text string of the version number you want to 
            use to filter LOINC codes for.

        :returns: A list of dictionaries containing LOINC lab result records
            including codes, terms, and axis information.
    """
    # if version is supplied we grab the delta 
    # and filter based upon version changes
    # otherwise grab all Obsersavtions
    if version != "":
        api_url = LOINC_BASE_URL + f"query=versionlastchanged:{version}+AND+" + LOINC_LAB_RESULT_QUERY
    else:
        api_url = LOINC_BASE_URL + f"query={LOINC_LAB_RESULT_QUERY}"
    loinc_vs_type = "Lab Results"
    loinc_result_rows = process_loinc_valueset(api_url, loinc_vs_type)
    # Now let's add the ConsumerName for each of the loinc codes
    loinc_result_rows = get_loinc_consumer_names(loinc_result_rows)
    return loinc_result_rows


def process_loinc_valueset(api_url, loinc_valueset_type):
    """Function that makes the LOINC API calls based upon the
        url and the loinc_Valueset_type passed in.  It confirms
        that the LOINC User/PWD are configured, makes the calls and then 
        passes the output into another function for more detailed processing.
        This function also performs the looping and row count maintanence as
        LOINC can only return 500 rows at a time.

        :param api_url: LOINC url for the specific API used for requesting
            data for LOINC codes.
        :param loinc_valueset_type: Distinguishes which LOINC codes are being 
            requested.  Options (Lab Names, Lab Orders, Lab Results, UMLS Atoms)

        :returns: A list of dictionaries containing LOINC code and term data
            or a list of UMLS URLS to pull additional information for each
            LOINC code.
    """
    if LOINC_USERNAME is None or LOINC_PWD is None:
        raise KeyError(
            "LOINC_USERNAME and LOINC_PWD environment variables are required to pull from LOINC!"
        )
    loinc_response = requests.get(api_url, auth=(LOINC_USERNAME, LOINC_PWD))
    if loinc_response.status_code != 200:
        # TODO: In Subsequent PR update this to be a logging statement
        print(
            f"ERROR Retrieving LOINC {loinc_valueset_type} CODES: {loinc_response.status_code}: {loinc_response.text}"
        )
        return None

    loinc_codes = loinc_response.json()
    loinc_rows = []
    loinc_umls_urls = {}

    record_count = loinc_codes["ResponseSummary"]["RecordsFound"]
    # TODO: In Subsequent PR update this to be a logging statement
    print(f"{loinc_valueset_type} Record Count: {record_count}")
    current_row_count = loinc_codes["ResponseSummary"]["RowsReturned"]
    next_url_call = loinc_codes["ResponseSummary"]["Next"]

    while current_row_count > 0:
        # Two pathways here - one is specific to getting all the UMLS Urls
        # for additional information from UMLS (SNOMED to LOINC Crosswalk and related terms)
        # - and the other specific for handling the standard LOINC API return data
        # into records that are digestable for TTC
        if loinc_valueset_type not in ("UMLS Atoms"):
            loinc_rows = process_loinc_results(loinc_codes["Results"], loinc_rows)
        else:
            loinc_umls_urls = get_loinc_umls_urls(loinc_codes["Results"], loinc_umls_urls)

        # handles the looping mechanism to get the next set of LOINC codes 
        # via the 'next' url
        if next_url_call is not None:
            next_loinc_response = requests.get(next_url_call, auth=(LOINC_USERNAME, LOINC_PWD))
            if next_loinc_response.status_code != 200:
                # TODO: In Subsequent PR update this to be a logging statement
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


def process_loinc_results(loinc_results, loinc_rows) -> dict:
    """Function that loops through the LOINC results, returned via the various
        API calls, and sends them into another function to extract and add
        all the different terms/names for each loinc code.

        :param loinc_results: The current iteration of LOINC data returned 
            from the API.  It will be empty if all results have been processed.
        :param loinc_rows: The list of 'processed' LOINC records, per code
            that are ready for TTC consumption.

        :returns: A list of dictionaries containing LOINC code, terms, and
            axis data.
    """
    if len(loinc_results) == 0:
        # TODO: In Subsequent PR update this to be a logging statement
        print("NO RESULTS TO PROCESS!")
        return loinc_rows

    for loinc_result in loinc_results:
        loinc_rows = get_all_loinc_terms_per_code(loinc_result, loinc_rows)

    return loinc_rows


def get_loinc_umls_urls(loinc_results, loinc_rows_list):
    """This function is used to generate and store the UMLS Urls that need
        to be used for each LOINC code.  They can be processed separately by another
        function.  Performance issues resulted in trying to do it all at once.

        :param loinc_results: The current iteration of LOINC data returned 
            from the API.
        :param loinc_rows: The list of UMLS 'processed' LOINC records, per code
            that are ready for UMLS processing.

        :returns: A list of dictionaries containing LOINC code, Long Name,
            and all the UMLS urls, per code, that are needed for UMLS processing.
    """

    # loop through all the LOINC codes for labs (orders and results)
    for loinc_result in loinc_results:
        # get the LOINC Code and the Long name for each LOINC concept
        # and store it for use in the UMLS urls
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
    """Process that constructs and makes the various API calls necessary to gather
        the UMLS data about the current LOINC codes.  The lower functions, related
        to ATOM/UMLS process are leveraged to extract and organize the data together
        for the enhancement/other LOINC files.

        :returns: A list of dictionaries that contain the various LOINC and
            UMLS data for each LOINC code, ready to be loaded into the enhancement file(s).
    """
    loinc_api_url = LOINC_BASE_URL + LOINC_LAB_NAMES_QUERY
    umls_loinc_results = process_loinc_valueset(loinc_api_url, "UMLS Atoms")
    return umls_loinc_results


def get_all_loinc_terms_per_code(loinc_result: dict, loinc_rows: list[dict]) -> dict:
    """This function receives the most recent result from the LOINC API
        and extracts the various terms/names and adds to the list of records
        ready for consumption into TTC model DB.

        :param loinc_results: The current iteration of LOINC data returned 
            from the API.
        :param loinc_rows: The list of 'processed' LOINC records, per code
            that are ready for TTC consumption.

        :returns: A list of dictionaries containing LOINC code, terms, and
            axis data.
    """
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

    loinc_rows.append(result_row)

    return loinc_rows


def get_loinc_consumer_names(loinc_rows):
    """Function that utilizes the downloaded consumer_names.csv file, in the 
        'other' data folder, to related the consumer name term with each loinc
        code.

        :param loinc_rows: The list of dictionaries that contain all the LOINC
            data (codes, terms/names, and axis information) so that this function
            can add the consumer name data to each record.

        :returns: The updated list of dictionaries of LOINC data records with
            the newly added consumer name term(s).
    """
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
        else:
            row["consumer_name"] = None
    return loinc_rows


def _filter_loinc_term(text: str) -> bool:
    """Function to determine if the input text is suppose to be filtered
        out of the LOINC terms/names based upon our understandings stored 
        in a list.
        (List: LOINC_TEXT_TO_FILTER).

        :param text: The LOINC term/name in question - should this text
            be filtered or not?

        :returns: boolean - true if it should be filtered and false if not
    """
    result: bool = False
    for filter_text in LOINC_TEXT_TO_FILTER:
        if filter_text in text:
            result = True
    return result


def get_loinc_current_version_data() -> (str, str):
    """Function Makes an API call to LOINC to determine current
        version and version date.
        
        :returns: str, str - LOINC version number, LOINC version Date
    """
    if LOINC_USERNAME is None or LOINC_PWD is None:
        raise KeyError(
            "LOINC_USERNAME and LOINC_PWD environment variables are required to pull from LOINC!"
        )
    loinc_response = requests.get(LOINC_META_URL, auth=(LOINC_USERNAME, LOINC_PWD))
    if loinc_response.status_code != 200:
        # TODO: In Subsequent PR update this to be a logging statement
        print(
            f"ERROR Retrieving LOINC META Data for current Version: {loinc_response.status_code}: {loinc_response.text}"
        )
        return None
    loinc_meta = json.loads(loinc_response.text)
    loinc_version_date = datetime.fromisoformat(loinc_meta["releaseDate"]).strftime("%Y-%m-%d")
    loinc_version = loinc_meta["version"]
    return loinc_version, loinc_version_date


def get_loinc_embedding_candidates(current_loinc_dict: dict, new_version: str) -> list[dict]:
    """Function compares New LOINC Version delta API response against the existing
        version of the TTC LOINC Lab Names (csv) filr to determine what changes are present.
        This function creates a change_log that will be used by another function to 
        contstruct a list of embedding candidates based upon the need for the different
        types of changes.  This change_log will also be used to record the updates in
        a delta file. 

        5 new candidate embedding records will be created for each 'NEW' LOINC code and
        a single candidate embedding record for each name/term change.  If the LOINC
        code changes from one lab type to another then we will create a record that 
        will simply update that records lab_type field via the Opensearch Index Load
        process. 

        Once this comparison is complete, a summary of the changes is then stored in a
        'delta' file in the 'data' folder to log/record the updates.
        
        This is currently just for the LOINC Lab Names data, but this can be
        modified to be more flexible for ALL LOINC extraction types as needed.

        :param current_loinc_dict: The current LOINC data, from the existing LOINC Lab Names
            csv file, loaded into an easier to compare dictionary structure.
        :param new_version: The string of the NEW LOINC version number to be used to 
            get the delta from the LOINC API call.

        :returns: boolean - true if it should be filtered and false if not
    """
    delta_extract_rows = get_loinc_lab_names(new_version)
    embedding_candidates = []
    change_log = {
                "New LOINC": 0,
                "short_name": 0,
                "long_name": 0,
                "display_name": 0,
                "full_name": 0,
                "consumer_name": 0,
                "LOINC Type": 0,
    }                  
    for update_loinc_record in delta_extract_rows:
        loinc_code = update_loinc_record['code']
        current_loinc_record = current_loinc_dict.get(loinc_code)
        changes = []

        if current_loinc_record is None:
            # new loinc code
            change_log["New LOINC"] += 1
            changes.append("New LOINC")
        elif current_loinc_record["lab_type"] != update_loinc_record["lab_type"]:
            change_log["LOINC Type"] += 1
            changes.append("LOINC Type")
        else:
            if current_loinc_record["short_name"].strip() != update_loinc_record["short_name"].strip():
                change_log["short_name"] += 1
                changes.append("short_name")
            if current_loinc_record["long_name"] != update_loinc_record["long_name"]:
                change_log["long_name"] += 1
                changes.append("long_name")
            if current_loinc_record["display_name"] != update_loinc_record["display_name"]:
                change_log["display_name"] += 1
                changes.append("display_name")
            if current_loinc_record["full_name"] != update_loinc_record["full_name"]:
                change_log["full_name"] += 1
                changes.append("full_name")
            if current_loinc_record["consumer_name"] != update_loinc_record["consumer_name"]:
                change_log["consumer_name"] += 1
                changes.append("consumer_name")
        embedding_candidates.extend(_create_embedding_candidates(loinc_code,update_loinc_record,changes))
    # TODO: In Subsequent PR update this to be a logging statement
    #  In PR for story #454 - this will be written to a file instead of printing
    print(f"EMB CANDIDATES: {len(embedding_candidates)} see counts of the various changes below")
    print(json.dumps(change_log, indent=4))
    return embedding_candidates


def _create_embedding_candidates(loinc_code: str, loinc_row: dict, element_changes: list[str]) -> list[dict]:
    """This function takes the loinc_code and a list of changes from a change_log,
        created by a higher function that performs the LOINC change comparison, and
        generates a list of embedding candidate records per LOINC Code.  As it is possible
        that a single LOINC code could have multiple term/name changes in a single LOINC
        update.
        
        5 new candidate embedding records will be created for each 'NEW' LOINC code and
        a single candidate embedding record for each name/term change.  If the LOINC
        code changes from one lab type to another then we will create a record that 
        will simply update that records lab_type field via the Opensearch Index Load
        process.

        :param loinc_code: The LOINC code that is either new or the existing one
            where changes are required.
        :param loinc_row: The actual LOINC data from the API for the LOINC code
            being added/updated.
        :param element_change: The list of changes required per LOINC code.

        :returns: a list of embedding candidate records for the LOINC code.
    """
    emb_candidates = []
    emb_candidate = {}
    short_name = loinc_row["short_name"]
    loinc_code = loinc_code
    loinc_type = loinc_row["lab_type"]
    property = loinc_row["property"]
    time_aspect = loinc_row["time_aspect"]
    system = loinc_row["system"]
    scale = loinc_row["scale_type"]
    method = loinc_row["method_type"]
    class_type = loinc_row["class_type"]
    long_name = loinc_row["long_name"]
    display_name = loinc_row["display_name"]
    full_name = loinc_row["full_name"]
    consumer_name = loinc_row["consumer_name"]

    emb_candidate["loinc_code"] = loinc_code
    emb_candidate["loinc_type"] = loinc_type
    emb_candidate["property"] = property
    emb_candidate["time"] = time_aspect
    emb_candidate["system"] = system
    emb_candidate["scale"] = scale
    emb_candidate["method"] = method
    emb_candidate["class"] = class_type

    # just add the whole row for each of the different 
    # terms used for embedding with the other fields
    # the same, when it's a NEW LOINC or the LOINC TYPE changes
    if (("LOINC Type" in element_changes or
        "New LOINC" in element_changes or
        "short_name" in element_changes)
        and short_name ):
        emb_candidate["loinc_name_type"] = "short_name"
        emb_candidate["term"] = short_name # same as codes or name_codes in embedding notebook
        emb_candidates.append(emb_candidate)
    if ("LOINC Type" in element_changes or
        "New LOINC" in element_changes or
        "long_name" in element_changes):
        emb_candidate["loinc_name_type"] = "long_name"
        emb_candidate["term"] = long_name # same as codes or name_codes in embedding notebook
        emb_candidates.append(emb_candidate)
    if ("LOINC Type" in element_changes or
        "New LOINC" in element_changes or
        "display_name" in element_changes):
        emb_candidate["loinc_name_type"] = "display_name"
        emb_candidate["term"] = display_name # same as codes or name_codes in embedding notebook
        emb_candidates.append(emb_candidate)
    if ("LOINC Type" in element_changes or
        "New LOINC" in element_changes or
        "full_name" in element_changes):
        emb_candidate["loinc_name_type"] = "full_name"
        emb_candidate["term"] = full_name # same as codes or name_codes in embedding notebook
        emb_candidates.append(emb_candidate)
    if ("LOINC Type" in element_changes or
        "New LOINC" in element_changes or
        "consumer_name" in element_changes):
        emb_candidate["loinc_name_type"] = "consumer_name"
        emb_candidate["term"] = consumer_name # same as codes or name_codes in embedding notebook
        emb_candidates.append(emb_candidate)
    return emb_candidates

