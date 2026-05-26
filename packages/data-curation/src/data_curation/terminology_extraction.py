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
from argparse import Namespace
from collections.abc import Callable, Iterator
from dataclasses import dataclass

import requests

from data_curation.terminologies.general import (
    BASE_FOLDER,
    ENHANCEMENTS_DIRECTORY,
    TMP_DIRECTORY,
    UMLS_API_KEY,
    clean_text_string,
)
from data_curation.terminologies.hl7 import get_hl7_encounter_act_codes, get_hl7_lab_interp
from data_curation.terminologies.loinc import (
    LOINC_PARTS_ABBRV_SYNONYMS,
    get_loinc_lab_names,
    get_loinc_lab_orders,
    get_loinc_lab_results,
    process_loincs_for_umls_urls,
)
from data_curation.terminologies.snomed import get_umls_snomed_lab_values
from data_curation.terminologies.vsac import (
    get_vsac_cvx_vaccines,
    get_vsac_rxnorm_medications,
    get_vsac_snomed_problems,
)

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


def _load_json_file(path: str) -> dict:
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"Error: {path} not found.")
        raise
    except json.JSONDecodeError:
        print(f"Error: Invalid JSON in {path}.")
        raise


def _umls_paged_results(url: str) -> Iterator[dict]:
    """Yield items from a paginated UMLS endpoint until exhausted."""
    page = 1
    while True:
        params = {
            "apiKey": UMLS_API_KEY,
            "pageNumber": page,
            "pageSize": _PAGE_SIZE,
            "language": "ENG",
        }
        response = requests.get(url, params=params, timeout=_TIMEOUT)
        if response.status_code != requests.codes.ok:
            return
        payload = response.json()
        yield from payload.get("result") or []
        page_count = payload.get("pageCount")
        if page_count is not None and page >= page_count:
            return
        page += 1


def _atom_name(item: dict) -> str | None:
    return item.get("name")


def _crosswalk_name(item: dict) -> str | None:
    if "LNC-" in (item.get("rootSource") or ""):
        return None
    return item.get("name")


def _collect_unique_names(url: str, name_of: Callable[[dict], str | None]) -> list[str]:
    """Walk a paged endpoint, extract names with `name_of`, dedupe and clean."""
    seen: list[str] = []
    for item in _umls_paged_results(url):
        name = name_of(item)
        if name and name not in seen:
            seen.append(clean_text_string(name))
    return seen


def _related_names_for(urls: dict) -> list[str]:
    """Combine UMLS atom + crosswalk related names for one LOINC code."""
    names = _collect_unique_names(urls["atom"], _atom_name)
    for name in _collect_unique_names(urls["crs"], _crosswalk_name):
        if name not in names:
            names.append(name)
    return names


def _process_loinc_codes_with_umls(file_path: str) -> dict:
    if UMLS_API_KEY is None:
        raise KeyError("UMLS_API_KEY environment variable must be set!")
    if not os.path.exists(TMP_DIRECTORY):
        raise KeyError("Directory where file is expected is missing!")

    umls_urls = _load_json_file(file_path)
    partial_path = TMP_DIRECTORY / "loinc_umls_related_names_PARTIAL.json"

    if not os.path.exists(partial_path):
        umls_loinc_rows = {}
    try:
        umls_loinc_rows = _load_json_file(partial_path)
    except (FileNotFoundError, json.JSONDecodeError):
        umls_loinc_rows = {}

    if umls_loinc_rows:
        print(f"Resuming — {len(umls_loinc_rows)} codes already processed.")
    print("Processing UMLS URLS for LOINC Codes!")

    processed_count = 0
    try:
        for loinc_code, urls_dict in umls_urls.items():
            long_name = urls_dict["long_name"]
            if long_name in umls_loinc_rows:
                continue  # already processed in a previous run

            related_names = _collect_unique_names(urls_dict["atom"], _atom_name)
            for name in _collect_unique_names(urls_dict["crs"], _crosswalk_name):
                if name not in related_names:
                    related_names.append(name)

            umls_loinc_rows[long_name] = {"code": loinc_code, "names": related_names}
            processed_count += 1

            if processed_count % 500 == 0:
                _save_json_file(TMP_DIRECTORY, partial_path.name, umls_loinc_rows, True)
                print(
                    f"{processed_count} new codes processed; "
                    f"{len(umls_loinc_rows)} total records in temp file."
                )
    except Exception:
        print("Unexpected error:", sys.exc_info()[0])
        print(f"Saving {len(umls_loinc_rows)} records in file!")
        _save_json_file(TMP_DIRECTORY, partial_path.name, umls_loinc_rows, False)
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
    args: Namespace,
) -> None:
    """Main entry point."""
    print("Starting Terminology ValueSet Sync...")

    all_vs: bool = args.all
    lab_orders: bool = args.lab_orders
    lab_obs: bool = args.lab_obs
    lab_values: bool = args.lab_values
    lab_interp: bool = args.lab_interp
    lab_names: bool = args.lab_names
    loinc_abbr_syn: bool = args.loinc_abbr_syn
    loinc_umls_syn: bool = args.loinc_umls_syn
    encounter_code: bool = args.encounter_code
    medication: bool = args.medication
    vaccine: bool = args.vaccine
    problem: bool = args.problem

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
    main(args)
