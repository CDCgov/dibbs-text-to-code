#!/usr/bin/env python

"""This script provides the ability to pull down various medical terminology valuesets required for processing eICR data, specifically adding codes to different data elements within an eICR message, such as Lab Order Name or Lab Result Interpretation.

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
from dataclasses import dataclass

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

_TIMEOUT = 61
_PAGE_SIZE = 500


def _extract_umls_full_snomed_lab_values() -> None:
    snomed_filename = f"snomed_lab_value_{datetime.datetime.now().strftime('%Y%m%d')}.csv"
    snomed_rows = get_umls_snomed_lab_values()
    _save_valueset_csv_file(snomed_filename, snomed_rows)


def _extract_full_hl7_lab_interp() -> None:
    hl7_filename = f"hl7_lab_interp_{datetime.datetime.now().strftime('%Y%m%d')}.csv"
    hl7_rows = get_hl7_lab_interp()
    _save_valueset_csv_file(hl7_filename, hl7_rows)


def _extract_full_loinc_lab_names() -> None:
    loinc_filename = f"loinc_lab_names_{datetime.datetime.now().strftime('%Y%m%d')}.csv"
    all_loinc_rows = get_loinc_lab_names()

    _save_valueset_csv_file(loinc_filename, all_loinc_rows, False)


def _extract_full_loinc_lab_orders() -> None:
    loinc_filename = f"loinc_lab_orders_{datetime.datetime.now().strftime('%Y%m%d')}.csv"
    loinc_order_rows = get_loinc_lab_orders()

    _save_valueset_csv_file(loinc_filename, loinc_order_rows, False)


def _extract_full_loinc_lab_results() -> None:
    loinc_filename = f"loinc_lab_result_{datetime.datetime.now().strftime('%Y%m%d')}.csv"
    loinc_result_rows = get_loinc_lab_results()
    _save_valueset_csv_file(loinc_filename, loinc_result_rows, False)


def _get_loinc_umls_related_results() -> None:
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
        print(f"LOINC RELATED NAMES URLS ADDED: {len(umls_loinc_results)}")
        _save_json_file(
            directory_path=TMP_DIRECTORY, filename=url_filename, contents=umls_loinc_results
        )
    else:
        print("LOINC UMLS URL File already exists!  Will use that for processing!")

    # now use the UMLS URLS to call the UMLS and get the related names
    # and store them in a file - first just a tmp file as the process takes a long time
    # but if the process fails, pick up the process from the last loinc code
    # from the tmp file
    umls_rows = _process_loinc_codes_with_umls(full_url_file_path)
    _save_json_file(ENHANCEMENTS_DIRECTORY, umls_filename, umls_rows, False)


def _process_loinc_codes_with_umls(file_path: str) -> dict:
    # ensure UMLS credentials are available
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
        print(f"Error: {file_path} not found. Please ensure the file exists.")
        raise
    except json.JSONDecodeError:
        print(f"Error: Invalid JSON format in {file_path}.")
        raise

    print("Processing UMLS URLS for LOINC Codes!")
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
                print("STARTING LOINC CODE: " + starting_loinc_code)
                process_loinc_code = False
        except FileNotFoundError:
            print(f"Error: {full_partial_file_path} not found. Please ensure the file exists.")
        except json.JSONDecodeError:
            print(f"Error: Invalid JSON format in {full_partial_file_path}.")

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
                    _save_json_file(TMP_DIRECTORY, umls_filename_tmp, umls_loinc_rows, True)
                    print(
                        f"{loinc_code_count} LOINC Codes have been processed and {len(umls_loinc_rows)} records have been written to a temp file!"
                    )

                # LOINC ATOMIC TERMS PROCESSING
                atom_page_num = 1
                lang = "ENG"
                params = {
                    "apiKey": UMLS_API_KEY,
                    "pageNumber": atom_page_num,
                    "pageSize": _PAGE_SIZE,
                    "language": lang,
                }

                umls_atom_response = requests.get(umls_atom_url, params=params, timeout=_TIMEOUT)
                atom_row_count = 0

                while umls_atom_response.status_code == requests.codes.ok:
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
                        "pageSize": _PAGE_SIZE,
                        "language": lang,
                    }

                    umls_atom_response = requests.get(
                        umls_atom_url, params=params, timeout=_TIMEOUT
                    )

                # LOINC CROSSWALK TERMS PROCESSING
                crs_page_num = 1
                lang = "ENG"
                params = {
                    "apiKey": UMLS_API_KEY,
                    "pageNumber": crs_page_num,
                    "pageSize": _PAGE_SIZE,
                    "language": lang,
                }
                umls_crs_response = requests.get(
                    umls_crs_url, params=params, timeout=_TIMEOUT
                ).json()
                crs_row_count = 0
                max_page = 1

                while (
                    umls_crs_response.status_code == requests.codes.ok and crs_page_num <= max_page
                ):
                    max_page = umls_crs_response.get("pageCount")
                    # NOTE: the UMLS responses are a bit slow
                    #  you can use the print statement below to get a
                    #  better idea of the progress if needed.
                    # print(f"Processing LOINC CROSSWALK page {crs_page_num}")
                    umls_crs_results = umls_crs_response.get("result")

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
                        "pageSize": _PAGE_SIZE,
                        "language": lang,
                    }

                    umls_crs_response = requests.get(umls_crs_url, params=params, timeout=_TIMEOUT)

                # add the record for the specific loinc code
                related_names_row = {"code": loinc_code, "names": related_names}
                umls_loinc_rows[long_name] = related_names_row
            if starting_loinc_code != "" and long_name == starting_loinc_code:
                process_loinc_code = True
    except:
        print("Unexpected error:", sys.exc_info()[0])
        print(f"Saving {len(umls_loinc_rows)} records in file!")
        # if exception occurs use all the rows in the existing list
        # to overwrite the entire partial file
        _save_json_file(TMP_DIRECTORY, umls_filename_tmp, umls_loinc_rows, False)
        raise
    return umls_loinc_rows


def _save_valueset_csv_file(filename: str, contents: dict, append_to_file: bool = False) -> None:
    if not filename.strip():
        print("No filename supplied.  Failed to save CSV file!")
        return

    if contents is None and len(contents) == 0:
        print("Empty file contents!  Failed to save CSV!")
        return

    file_method = "a" if append_to_file else "w"

    try:
        full_file_path = BASE_FOLDER / filename
        csv_headers = contents[0].keys()

        with open(full_file_path, file_method, newline="", encoding="utf-8") as csv_file:
            writer = csv.DictWriter(csv_file, csv_headers, delimiter="|")
            if not (append_to_file):
                writer.writeheader()
            writer.writerows(contents)
        print(f"CSV File successfully saved as {full_file_path}")

    except ValueError as e:
        print(f"Error parsing Dict Contents: {e}")
    except Exception as e:
        print(f"An error occurred: {e}")


def _save_json_file(
    directory_path: str, filename: str, contents: dict, append_to_file: bool = False
) -> None:
    if not filename.strip() or not directory_path.strip():
        print("No filename & path supplied.  Failed to save JSON File!")
        return

    if contents is None and len(contents) == 0:
        print("Empty file contents!  Failed to save JSON File!")
        return

    if not os.path.exists(directory_path):
        os.makedirs(directory_path)

    full_file_path = directory_path / filename

    file_method = "a" if append_to_file else "w"

    try:
        with open(full_file_path, file_method, encoding="utf-8") as dict_file:
            json.dump(contents, dict_file, indent=4)
        print(f"JSON File successfully saved as: {full_file_path}")

    except ValueError as e:
        print(f"Error parsing Dict Contents: {e}")
    except Exception as e:
        print(f"An error occurred: {e}")


_INVALID_VALUES = frozenset({None, "", "$"})
_AXIS_NAMES = ("component", "method", "property", "scale", "system", "time")


@dataclass(frozen=True)
class PartRecord:
    """One row from the LOINC parts CSV, normalized."""

    code: str
    name: str
    axis: str
    repl_name: str | None
    pref_abrv: str | None
    synonym: str | None

    @classmethod
    def from_csv_row(cls, row: dict) -> "PartRecord":
        """Create a PartRecord from a CSV row dictionary."""
        return cls(
            code=row.get("PART_NUM"),
            name=row.get("PART"),
            axis=(row.get("PART_TYPE_NAME_NAME") or "").lower(),
            repl_name=row.get("PART_NAME"),
            pref_abrv=row.get("PREF_ABRV"),
            synonym=row.get("SYNONYM"),
        )


def _should_add(value: str | None, part_name: str, *existing_lists: list) -> bool:
    """True if `value` is a real new entry: non-empty, not the part name itself, and not already present in any of the given lists."""
    if value in _INVALID_VALUES or value == part_name:
        return False
    return all(value not in lst for lst in existing_lists)


def _create_loinc_part_abbrv_syn_dicts() -> None:
    """Creates one JSON file per LOINC part axis containing each Part Code, Name, Abbreviations and Synonyms."""
    today = datetime.datetime.now().strftime("%Y%m%d")
    part_dicts: dict[str, dict] = {axis: {} for axis in _AXIS_NAMES}

    row_count = 0
    with open(LOINC_PARTS_ABBRV_SYNONYMS, encoding="utf-8") as file:
        reader = csv.DictReader(file, delimiter="|")
        for row in reader:
            row_count += 1
            record = PartRecord.from_csv_row(row)
            target = part_dicts.get(record.axis)
            if target is None:
                continue  # unknown axis — skip silently

            existing = target.setdefault(
                record.name,
                {"code": record.code, "abbrv": [], "synonyms": []},
            )

            if existing.get("code") != record.code:
                target[record.name] = existing

            synonyms = list(existing["synonyms"])
            abbrv = list(existing["abbrv"])

            if _should_add(record.repl_name, record.name, synonyms):
                synonyms.append(record.repl_name)
            if _should_add(record.pref_abrv, record.name, synonyms, abbrv):
                abbrv.append(record.pref_abrv)
            if _should_add(record.synonym, record.name, synonyms, abbrv):
                synonyms.append(record.synonym)

            target[record.name] = {**existing, "synonyms": synonyms, "abbrv": abbrv}

    print(f"Total Rows Processed: {row_count}")

    for axis, data in part_dicts.items():
        filename = f"loinc_{axis}_abbrv_syn_{today}.json"
        _save_json_file(ENHANCEMENTS_DIRECTORY, filename, data)


def _extract_full_hl7_encounter_act_codes() -> None:
    hl7_filename = f"hl7_encounter_code_{datetime.datetime.now().strftime('%Y%m%d')}.csv"
    hl7_rows = get_hl7_encounter_act_codes()
    _save_valueset_csv_file(hl7_filename, hl7_rows)


def _extract_full_vsac_rxnorm_medications() -> None:
    medication_filename = (
        f"vsac_rxnorm_medications_{datetime.datetime.now().strftime('%Y%m%d')}.csv"
    )
    data_rows = get_vsac_rxnorm_medications()
    _save_valueset_csv_file(medication_filename, data_rows)


def _extract_full_vsac_cvx_vaccines() -> None:
    vaccine_filename = f"vsac_cvx_vaccines_{datetime.datetime.now().strftime('%Y%m%d')}.csv"
    data_rows = get_vsac_cvx_vaccines()
    _save_valueset_csv_file(vaccine_filename, data_rows)


# problems are also known as "Diagnosis/Symptom Codes"
def _extract_full_vsac_snomed_problems() -> None:
    problem_filename = f"vsac_snomed_problems_{datetime.datetime.now().strftime('%Y%m%d')}.csv"
    data_rows = get_vsac_snomed_problems()
    _save_valueset_csv_file(problem_filename, data_rows)


def main(
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
    """Main entry point."""
    print("Starting Terminology ValueSet Sync...")
    if all_vs or lab_orders:
        print("Getting LOINC Lab Orders...")
        _extract_full_loinc_lab_orders()
    if all_vs or lab_obs:
        print("Getting LOINC Lab Observations...")
        _extract_full_loinc_lab_results()
    if all_vs or lab_values:
        print("Getting SNOMED Lab Result Values...")
        _extract_umls_full_snomed_lab_values()
    if all_vs or lab_interp:
        print("Getting HL7 Lab Result Interpretations...")
        _extract_full_hl7_lab_interp()
    if all_vs or lab_names:
        print("Getting LOINC Lab Names...")
        _extract_full_loinc_lab_names()
    if all_vs or loinc_abbr_syn:
        print("Getting LOINC Part Abbreviations & Synonyms...")
        _create_loinc_part_abbrv_syn_dicts()
    if all_vs or loinc_umls_syn:
        print("Getting LOINC UMLS Related Names...")
        _get_loinc_umls_related_results()
    if all_vs or encounter_code:
        print("Getting HL7 Encounter Act Codes...")
        _extract_full_hl7_encounter_act_codes()
    if all_vs or medication:
        print("Getting VSAC RXNORM Medication Codes...")
        _extract_full_vsac_rxnorm_medications()
    if all_vs or vaccine:
        print("Getting VSAC CVX Vaccine Codes...")
        _extract_full_vsac_cvx_vaccines()
    if all_vs or problem:
        print("Getting VSAC SNOMED Problem (Diagnosis/Symptom) Codes...")
        _extract_full_vsac_snomed_problems()


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
        help="For Loinc Part Abbreviations and Synonyms",
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
