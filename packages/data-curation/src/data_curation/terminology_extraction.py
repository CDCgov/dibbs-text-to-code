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
    - Encounter Codes - HL7
    - Medication Codes - VSAC/RXNorm
    - Vaccinations - VSAC
    - Problems/Diagnosis - VSAC

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

from data_curation.terminologies.general import BASE_FOLDER
from data_curation.terminologies.general import ENHANCEMENTS_DIRECTORY
from data_curation.terminologies.general import TMP_DIRECTORY
from data_curation.terminologies.general import UMLS_API_KEY
from data_curation.terminologies.general import clean_text_string
from data_curation.terminologies.hl7 import get_hl7_encounter_act_codes
from data_curation.terminologies.hl7 import get_hl7_lab_interp
from data_curation.terminologies.loinc import LOINC_PARTS_ABBRV_SYNONYMS
from data_curation.terminologies.loinc import get_loinc_lab_names
from data_curation.terminologies.loinc import get_loinc_lab_orders
from data_curation.terminologies.loinc import get_loinc_lab_results
from data_curation.terminologies.loinc import process_loincs_for_umls_urls
from data_curation.terminologies.snomed import get_umls_snomed_lab_values
from data_curation.terminologies.vsac import get_vsac_cvx_vaccines
from data_curation.terminologies.vsac import get_vsac_rxnorm_medications
from data_curation.terminologies.vsac import get_vsac_snomed_problems

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


def extract_umls_full_snomed_lab_values() -> None:  # noqa: D103
    snomed_filename = f"snomed_lab_value_{datetime.datetime.now().strftime('%Y%m%d')}.csv"
    snomed_rows = get_umls_snomed_lab_values()
    save_valueset_csv_file(snomed_filename, snomed_rows)


def extract_full_hl7_lab_interp() -> None:  # noqa: D103
    hl7_filename = f"hl7_lab_interp_{datetime.datetime.now().strftime('%Y%m%d')}.csv"
    hl7_rows = get_hl7_lab_interp()
    save_valueset_csv_file(hl7_filename, hl7_rows)


def extract_full_loinc_lab_names() -> None:  # noqa: D103
    loinc_filename = f"loinc_lab_names_{datetime.datetime.now().strftime('%Y%m%d')}.csv"
    all_loinc_rows = get_loinc_lab_names()

    save_valueset_csv_file(loinc_filename, all_loinc_rows, False)


def extract_full_loinc_lab_orders() -> None:  # noqa: D103
    loinc_filename = f"loinc_lab_orders_{datetime.datetime.now().strftime('%Y%m%d')}.csv"
    loinc_order_rows = get_loinc_lab_orders()

    save_valueset_csv_file(loinc_filename, loinc_order_rows, False)


def extract_full_loinc_lab_results() -> None:  # noqa: D103
    loinc_filename = f"loinc_lab_result_{datetime.datetime.now().strftime('%Y%m%d')}.csv"
    loinc_result_rows = get_loinc_lab_results()
    save_valueset_csv_file(loinc_filename, loinc_result_rows, False)


def get_loinc_umls_related_results() -> None:  # noqa: D103
    if UMLS_API_KEY is None:
        raise KeyError("UMLS_API_KEY Environment Variable must be set to a proper UMLS API Key!")

    url_filename = "loinc_umls_related_names_urls.json"
    umls_filename = f"loinc_umls_related_names_{datetime.datetime.now().strftime('%Y%m%d')}.json"
    full_url_file_path = TMP_DIRECTORY / url_filename

    # handle the first step of the process - find all the loinc codes
    # and generate the two different URLS specific for UMLS API
    # then store them in a file
    if not os.path.exists(full_url_file_path):
        umls_loinc_results = process_loincs_for_umls_urls()
        save_json_file(
            directory_path=TMP_DIRECTORY, filename=url_filename, contents=umls_loinc_results
        )
    else:
        pass

    # now use the UMLS URLS to call the UMLS and get the related names
    # and store them in a file - first just a tmp file as the process takes a long time
    # but if the process fails, pick up the process from the last loinc code
    # from the tmp file
    umls_rows = process_loinc_codes_with_umls(full_url_file_path)
    save_json_file(ENHANCEMENTS_DIRECTORY, umls_filename, umls_rows, False)


def process_loinc_codes_with_umls(file_path: str) -> dict:  # noqa: D103
    # ensure UMLS creds are available
    if UMLS_API_KEY is None:
        raise KeyError("UMLS_API_KEY Environment Variable must be set to a proper UMLS API Key!")

    # ensure the tmp directory exists for both the UMLS URLS
    # as well as the temp file to store progress
    if not os.path.exists(TMP_DIRECTORY):
        raise KeyError("Directory where file is expected is missing!")

    # load UMLS URLS
    try:
        with open(file_path) as file:
            umls_urls = json.load(file)
    except FileNotFoundError:
        raise
    except json.JSONDecodeError:
        raise

    umls_loinc_rows = {}
    loinc_code_count = 0

    process_loinc_code = True
    starting_loinc_code = ""
    umls_filename_tmp = "loinc_umls_related_names_PARTIAL.json"
    full_partial_file_path = TMP_DIRECTORY / umls_filename_tmp

    if os.path.exists(full_partial_file_path):
        try:
            with open(full_partial_file_path, newline="", encoding="utf-8") as file:
                umls_loinc_rows = json.load(file)
                starting_loinc_code = list(umls_loinc_rows)[-1]
                process_loinc_code = False
        except FileNotFoundError:
            pass
        except json.JSONDecodeError:
            pass

    try:
        # loop through all the LOINC codes in dict along
        # with all the correlated umls urls
        for loinc_code, urls_dict in umls_urls.items():
            long_name = urls_dict["long_name"]
            if process_loinc_code:
                umls_atom_url = urls_dict["atom"]
                umls_crs_url = urls_dict["crs"]
                related_names = []
                loinc_code_count += 1

                # every 500 loinc code store the results
                # in a temp file to ensure progress is not lost
                # if we need to restart (typical run is 36 Hours)
                if loinc_code_count % 500 == 0:
                    save_json_file(TMP_DIRECTORY, umls_filename_tmp, umls_loinc_rows, True)

                # LOINC ATOMIC TERMS PROCESSING
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
                        if related_name and related_name not in related_names:
                            related_names.append(clean_text_string(related_name))
                            atom_row_count += 1

                    atom_page_num += 1
                    params = {
                        "apiKey": UMLS_API_KEY,
                        "pageNumber": atom_page_num,
                        "pageSize": page_size,
                        "language": lang,
                    }

                    umls_atom_response = requests.get(umls_atom_url, params=params)

                # LOINC CROSSWALK TERMS PROCESSING
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
                        if (
                            "LNC-" not in root_source
                            and related_name
                            and related_name not in related_names
                        ):
                            related_names.append(clean_text_string(related_name))
                            crs_row_count += 1

                    crs_page_num += 1
                    params = {
                        "apiKey": UMLS_API_KEY,
                        "pageNumber": crs_page_num,
                        "pageSize": page_size,
                        "language": lang,
                    }

                    umls_crs_response = requests.get(umls_crs_url, params=params)

                # add the record for the specific loinc code
                related_names_row = {"code": loinc_code, "names": related_names}
                umls_loinc_rows[long_name] = related_names_row
            if starting_loinc_code != "" and long_name == starting_loinc_code:
                process_loinc_code = True
    except:
        # if exception occurs use all the rows in the existing list
        # to overwrite the entire partial file
        save_json_file(TMP_DIRECTORY, umls_filename_tmp, umls_loinc_rows, False)
        raise
    return umls_loinc_rows


def save_valueset_csv_file(filename: str, contents: dict, append_to_file: bool = False) -> None:  # noqa: D103
    if not filename.strip():
        return

    if contents is None and len(contents) == 0:
        return

    file_method = "a" if append_to_file else "w"

    try:
        full_file_path = BASE_FOLDER / filename
        csv_headers = contents[0].keys()

        with open(full_file_path, file_method, newline="", encoding="utf-8") as csvfile:
            writer = csv.DictWriter(csvfile, csv_headers, delimiter="|")
            if not (append_to_file):
                writer.writeheader()
            writer.writerows(contents)

    except ValueError:
        pass
    except Exception:
        pass


def save_json_file(  # noqa: D103
    directory_path: str, filename: str, contents: dict, append_to_file: bool = False
) -> None:
    if not filename.strip() or not directory_path.strip():
        return

    if contents is None and len(contents) == 0:
        return

    if not os.path.exists(directory_path):
        os.makedirs(directory_path)

    full_file_path = directory_path / filename

    file_method = "a" if append_to_file else "w"

    try:
        with open(full_file_path, file_method, encoding="utf-8") as dictfile:
            json.dump(contents, dictfile, indent=4)

    except ValueError:
        pass
    except Exception:
        pass


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


def create_loinc_part_abbrv_syn_dicts() -> None:
    """Creates single file dictionary for each of the different
    LOINC parts, which contains each LOINC Part Code, Name
    and Abbreviations and Synonyms.
    """
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

    with open(LOINC_PARTS_ABBRV_SYNONYMS, encoding="utf-8") as file:
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
    # write each dict out into it's own file
    save_json_file(ENHANCEMENTS_DIRECTORY, component_file, component_dict)
    save_json_file(ENHANCEMENTS_DIRECTORY, method_file, method_dict)
    save_json_file(ENHANCEMENTS_DIRECTORY, property_file, property_dict)
    save_json_file(ENHANCEMENTS_DIRECTORY, system_file, system_dict)
    save_json_file(ENHANCEMENTS_DIRECTORY, time_file, time_dict)
    save_json_file(ENHANCEMENTS_DIRECTORY, scale_file, scale_dict)


def extract_full_hl7_encounter_act_codes() -> None:  # noqa: D103
    hl7_filename = f"hl7_encounter_code_{datetime.datetime.now().strftime('%Y%m%d')}.csv"
    hl7_rows = get_hl7_encounter_act_codes()
    save_valueset_csv_file(hl7_filename, hl7_rows)


def extract_full_vsac_rxnorm_medications() -> None:  # noqa: D103
    medication_filename = (
        f"vsac_rxnorm_medications_{datetime.datetime.now().strftime('%Y%m%d')}.csv"
    )
    data_rows = get_vsac_rxnorm_medications()
    save_valueset_csv_file(medication_filename, data_rows)


def extract_full_vsac_cvx_vaccines() -> None:  # noqa: D103
    vaccine_filename = f"vsac_cvx_vaccines_{datetime.datetime.now().strftime('%Y%m%d')}.csv"
    data_rows = get_vsac_cvx_vaccines()
    save_valueset_csv_file(vaccine_filename, data_rows)


# problems are also known as "Diagnosis/Symptom Codes"
def extract_full_vsac_snomed_problems() -> None:  # noqa: D103
    problem_filename = f"vsac_snomed_problems_{datetime.datetime.now().strftime('%Y%m%d')}.csv"
    data_rows = get_vsac_snomed_problems()
    save_valueset_csv_file(problem_filename, data_rows)


def main(  # noqa: D103
    all_vs: bool,
    lab_orders: bool,
    lab_obs: bool,
    lab_values: bool,
    lab_interp: bool,
    lab_names: bool,
    loinc_abbr_syn: bool,
    loinc_umls_syn: bool,
    encounter_code: bool,
    medication: bool,
    vaccine: bool,
    problem: bool,
) -> None:
    if all_vs or lab_orders:
        extract_full_loinc_lab_orders()
    if all_vs or lab_obs:
        extract_full_loinc_lab_results()
    if all_vs or lab_values:
        extract_umls_full_snomed_lab_values()
    if all_vs or lab_interp:
        extract_full_hl7_lab_interp()
    if all_vs or lab_names:
        extract_full_loinc_lab_names()
    if all_vs or loinc_abbr_syn:
        create_loinc_part_abbrv_syn_dicts()
    if all_vs or loinc_umls_syn:
        get_loinc_umls_related_results()
    if all_vs or encounter_code:
        extract_full_hl7_encounter_act_codes()
    if all_vs or medication:
        extract_full_vsac_rxnorm_medications()
    if all_vs or vaccine:
        extract_full_vsac_cvx_vaccines()
    if all_vs or problem:
        extract_full_vsac_snomed_problems()


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
    parser.add_argument(
        "--encounter_code",
        action="store_true",
        help="For HL7 Encounter Act Codes",
    )
    parser.add_argument(
        "--medication",
        action="store_true",
        help="For VSAC RXNORM Medication Codes",
    )
    parser.add_argument(
        "--vaccine",
        action="store_true",
        help="For VSAC CVX Vaccine Codes",
    )
    parser.add_argument(
        "--problem",
        action="store_true",
        help="For VSAC SNOMED Problem (Diagnosis/Symptom) Codes",
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
        args.encounter_code,
        args.medication,
        args.vaccine,
        args.problem,
    )
