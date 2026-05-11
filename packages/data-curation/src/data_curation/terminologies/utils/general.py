#!/usr/bin/env python"""

"""
data_curation.terminologies.utils.general
~~~~~~~~~~~~~~~~~~~~~~~~~

This module contains a number of helper functions designed to assist
with the process of extracting Medical Terminology codes and their terms 
to generate and maintain embeddings in Opensearch for TTC.
"""

# File & Directories
import csv
from datetime import datetime
import json
import os
import re



SNOINC_DIRECTORY = "./data/snoinc_extracts"
SNOINC_ENHANCEMENTS_DIRECTORY = "./data/snoinc_extracts/enhancements"
SNOINC_CHANGES_DIRECTORY = "./data/snoinc_extracts/change_log"
SNOINC_ARCHIVE_DIRECTORY = "./data/snoinc_extracts/archive"
TMP_DIRECTORY = "./tmp"
MULTIPLE_SPACE = re.compile(r"\s+")

UMLS_API_KEY = os.environ.get("UMLS_API_KEY")


def clean_text_string(value: str) -> str:
    if value is not None:
        return re.sub(MULTIPLE_SPACE, " ", value).strip()
    else:
        return ""


def get_date_from_latest_filename(filename: str, terminology: str) -> str:
    file_date = re.search(r'\d{8}', filename).group()

    if terminology == 'loinc':
        return datetime.strptime(file_date, "%Y%m%d").strftime("%Y-%m-%d")


def get_latest_extract_file_name(filename_prefix: str):
    files = [f for f in os.listdir(SNOINC_DIRECTORY) if f.startswith(filename_prefix)]
    if files:
        latest_file = max(files)
    return latest_file


def load_extract_file_to_dict(filename: str) -> list[dict]:
    file_path = os.path.join(SNOINC_DIRECTORY, filename)
    extract_dict = {}
    with open(file_path, mode='r', encoding="utf-8") as file:
        reader = csv.DictReader(file, delimiter="|")
        #extract_dict_list = list(reader)
        extract_dict = {row['code']: row for row in reader}
    
    return extract_dict


def save_valueset_csv_file(filename: str, contents: dict, append_to_file: bool = False):  # noqa: D103
    if not filename.strip():
        print("No filename supplied.  Failed to save CSV file!")
        return

    if contents is None and len(contents) == 0:
        print("Empty file contents!  Failed to save CSV!")
        return

    if not os.path.exists(SNOINC_DIRECTORY):
        os.makedirs(SNOINC_DIRECTORY)

    if append_to_file:
        file_method = "a"
    else:
        file_method = "w"

    try:
        full_file_path = os.path.join(SNOINC_DIRECTORY, filename)
        csv_headers = contents[0].keys()

        with open(full_file_path, file_method, newline="", encoding="utf-8") as csvfile:
            writer = csv.DictWriter(csvfile, csv_headers, delimiter="|")
            if not (append_to_file):
                writer.writeheader()
            writer.writerows(contents)
        print(f"CSV File successfully saved as {full_file_path}")

    except ValueError as e:
        print(f"Error parsing Dict Contents: {e}")
    except Exception as e:
        print(f"An error occured: {e}")


def save_json_file(  # noqa: D103
    directory_path: str, filename: str, contents: dict, append_to_file: bool = False
):
    if not filename.strip() or not directory_path.strip():
        print("No filename & path supplied.  Failed to save JSON File!")
        return

    if contents is None and len(contents) == 0:
        print("Empty file contents!  Failed to save JSON File!")
        return

    if not os.path.exists(directory_path):
        os.makedirs(directory_path)

    full_file_path = os.path.join(directory_path, filename)

    if append_to_file:
        file_method = "a"
    else:
        file_method = "w"

    try:
        with open(full_file_path, file_method, encoding="utf-8") as dictfile:
            json.dump(contents, dictfile, indent=4)
        print(f"JSON File successfully saved as: {full_file_path}")

    except ValueError as e:
        print(f"Error parsing Dict Contents: {e}")
    except Exception as e:
        print(f"An error occured: {e}")


def archive_valueset_file(file_name: str):
    source_path = os.path.join(SNOINC_DIRECTORY, file_name)
    target_path = os.path.join(SNOINC_ARCHIVE_DIRECTORY, file_name)

    if os.path.exists(source_path) and os.path.isfile(source_path):
        os.rename(source_path, target_path)

