#!/usr/bin/env python

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
from pathlib import Path
from utils.regex_patterns import MULTIPLE_SPACE
import re


# Value Set Directories
BASE_FOLDER = Path(__file__).parents[5] / "data" / "snoinc_extracts"
ENHANCEMENTS_DIRECTORY = BASE_FOLDER / "enhancements"
TMP_DIRECTORY = Path(__file__).parents[5] / "tmp"

# Keys - the UMLS key is used for more than 
#   one terminology set so it's here in General
UMLS_API_KEY = os.environ.get("UMLS_API_KEY")


def clean_text_string(value: str) -> str:
    """Function that removes multiple space characters from a string
        and returns it for further processing.

        :param value: Text string that needs to be clean.

        :returns: A text string that has spaces removed. Returns ""
            if value input is empty or None.
    """
    if value is not None:
        return re.sub(MULTIPLE_SPACE, " ", value).strip()
    else:
        return ""


def get_date_from_filename(filename: str, terminology: str) -> str:
    """Function that extracts and formats the date from any of
        the value set extract files and formats the date string
        into a pattern used by the terminology set in their Versioning API call
        (ie. get the latest version and version date).

        :param filename: Text of the filename to extact the date from.
        :param terminology: The name of the value set in question as the
            date formats may have different requirements based upon
            the API response for said value set.

        :returns: A formatted date string that can be used for comparison
            to determine if an update is required.
    """
    match = re.search(r'\d{8}', filename)
    if match is None:
        raise ValueError(f"Unable to extract 8 digit date from file name: {filename}!")
    
    file_date = match.group()

    # date comparison for LOINC requires date in YYYY-MM-DD format
    if terminology == 'loinc':
        return datetime.strptime(file_date, "%Y%m%d").strftime("%Y-%m-%d")
    # for all other terminologies, yet to be determined
    # return date from file in YYYYMMDD format
    else:
        return datetime.strptime(file_date, "%Y%m%d").strftime("%Y%m%d")


def get_latest_extract_file_name(filename_prefix: str):
    """Function that gets the most current/recent value set csv 
        file from the TTC code repo, by filename prefix.

        :param filename_prefix: The part of the filename that defines the
            terminology value set type (ie. loinc_lab_names) that you want
            to find the most recent file of.

        :returns: The file name and file path of the most recent value set
            extract file.
    """
    if filename_prefix is None:
        return None
    
    files = [f for f in os.listdir(BASE_FOLDER) if f.startswith(filename_prefix)]
    if filename_prefix != "" and files:
        latest_file = max(files)
        return latest_file
    else:
        raise FileNotFoundError(f"No file with prefix {filename_prefix} under {BASE_FOLDER}!")


def load_extract_file_to_dict(filename: str) -> list[dict]:
    """Function that takes a filename, finds the file and parses
        it into an easier to process dictionary.

        :param filename: The filename of the file you wanted parsed
            into a dictionary.

        :returns: A dictionary of the data pulled from a csv file.
    """
    if not filename or filename =="":
        return {}
    file_path = BASE_FOLDER / filename
    extract_dict = {}
    if file_path.exists():
        with open(file_path, mode='r', encoding="utf-8") as file:
            reader = csv.DictReader(file, delimiter="|")
            extract_dict = {row['code']: row for row in reader}
    
    return extract_dict


def save_valueset_csv_file(filename: str, contents: dict, append_to_file: bool = False):  # noqa: D103
    if not filename.strip():
        print("No filename supplied.  Failed to save CSV file!")
        return

    if contents is None and len(contents) == 0:
        print("Empty file contents!  Failed to save CSV!")
        return

    if append_to_file:
        file_method = "a"
    else:
        file_method = "w"

    try:
        full_file_path = BASE_FOLDER / filename
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

    full_file_path = directory_path / filename

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
