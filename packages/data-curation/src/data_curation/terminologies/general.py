#!/usr/bin/env python

"""This module contains a number of helper functions designed to assist with the process of extracting Medical Terminology codes and their terms to generate and maintain embeddings in Opensearch for TTC."""

# File & Directories
import csv
import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import TypedDict

from utils.regex_patterns import MULTIPLE_SPACE

# Value Set Directories
BASE_FOLDER = Path(__file__).parents[5] / "data" / "snoinc_extracts"
ENHANCEMENTS_DIRECTORY = BASE_FOLDER / "enhancements"
TMP_DIRECTORY = Path(__file__).parents[5] / "tmp"
CHANGE_LOG_DIRECTORY = BASE_FOLDER / "change_log"

# Keys - the UMLS key is used for more than
#   one terminology set so it's here in General
UMLS_API_KEY = os.environ.get("UMLS_API_KEY")


class TerminologyUpdateResponse(TypedDict):
    """Defines dictionary for Terminology Update Response."""

    terminology: list[str]
    result: str
    message: str
    change_log: dict
    embedding_records: list[dict]


def clean_text_string(value: str | None) -> str:
    """Function that removes multiple space characters from a string and returns it for further processing.

    :param value: Text string that needs to be clean.

    :returns: A text string that has spaces removed. Returns ""
        if value input is empty or None.
    """
    if value is not None:
        return re.sub(MULTIPLE_SPACE, " ", value).strip()
    return ""


def get_date_from_file_name(file_name: str, terminology: str) -> str:
    """Function that extracts and formats the date from the name of any value set extract file and formats the date string into a pattern used by the terminology set in their Versioning API call (ie. get the latest version and version date).

    :param file_name: Text of the file name to extact the date from.
    :param terminology: The name of the value set in question as the
        date formats may have different requirements based upon
        the API response for said value set.

    :returns: A formatted date string that can be used for comparison
        to determine if an update is required.
    """
    match = re.search(r"\d{8}", file_name)
    if match is None:
        raise ValueError(f"Unable to extract 8 digit date from file name: {file_name}!")

    file_date = match.group()

    # date comparison for LOINC requires date in YYYY-MM-DD format
    if terminology == "loinc":
        return datetime.strptime(file_date, "%Y%m%d").strftime("%Y-%m-%d")
    # for all other terminologies, yet to be determined
    # return date from file in YYYYMMDD format
    return datetime.strptime(file_date, "%Y%m%d").strftime("%Y%m%d")


def get_latest_local_extract_file_name(file_name_prefix: str | None) -> str | None:
    """Function that gets the most current/recent value set csv file name from the TTC code repo, by file name prefix.

    :param file_name_prefix: The part of the file name that defines the
        terminology value set type (ie. loinc_lab_names) that you want
        to find the most recent file of.

    :returns: The file name and file path of the most recent value set
        extract file.
    """
    if file_name_prefix is None:
        return None

    # TODO: This will need to change to pull the file
    # from the S3 Bucket and return the file name
    files = [f for f in os.listdir(BASE_FOLDER) if f.startswith(file_name_prefix)]
    if file_name_prefix != "" and files:
        latest_file = max(files)
        return latest_file
    raise FileNotFoundError(f"No file with prefix {file_name_prefix} under {BASE_FOLDER}!")


def load_local_extract_file_to_dict(file_name: str | None) -> dict[str, dict[str, str]]:
    """Function that takes a file name, finds the file and parses it into an easier to process dictionary.

    :param file_name: The file name of the file you wanted parsed
        into a dictionary.

    :returns: A dictionary of the data pulled from a csv file.
    """
    # TODO: This will need to change to pull the file
    # from the S3 Bucket and load the contents into
    # a dict
    if not file_name or file_name == "":
        return {}
    file_path = BASE_FOLDER / file_name
    extract_dict = {}
    if file_path.exists():
        with open(file_path, encoding="utf-8") as file:
            reader = csv.DictReader(file, delimiter="|")
            extract_dict = {row["code"]: row for row in reader}

    return extract_dict


def save_valueset_csv_file(
    file_name: str, contents: list[dict], append_to_file: bool = False
) -> None:
    """Function that takes a file name, which includes the directory, and contents (dictionary) for the file then writes the results out into a standard csv file with a '|' delimiter - specifically for terminology extract files.

    :param file_name: The directory location and file name of the file
        you wanted created.
    :param contents: The dictionary containing the data that will be
        paresed into a csv file.  The keys will be the column name
        headers for the csv file.
    :param append_to_file: Boolean - Do you want to overwrite the file or append?
        Default is set to False, so overwrite the file.

    :returns: Nothing.
    """
    # TODO: This will need to change to write the csv
    # file into an S3 bucket
    # maybe will need a service for all the S3 work?
    if not file_name.strip():
        print("No file name supplied.  Failed to save CSV file!")
        return

    if contents is None or len(contents) == 0:
        print("Empty file contents!  Failed to save CSV!")
        return

    file_method = "a" if append_to_file else "w"

    try:
        full_file_path = BASE_FOLDER / file_name
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


def save_json_file(
    directory_path: str | Path,
    file_name: str,
    contents: dict | list[dict],
    append_to_file: bool = False,
) -> None:
    """Function that takes a file name, directory path, and contents (dictionary) for the file then writes the results out into a basic JSON file using the dictionary as the structure.

    :param file_name: The directory location and file name of the file
        you wanted created.
    :param contents: The dictionary containing the data that will be
        paresed into a json file.
    :param append_to_file: Boolean - Do you want to overwrite the file or append?
        Default is set to False, so overwrite the file.

    :returns: Nothing.
    """
    # TODO: This will need to change to write the csv
    # file into an S3 bucket
    # maybe will need a service for all the S3 work?
    if not file_name.strip() or not directory_path:
        print("No file name & path supplied.  Failed to save JSON File!")
        return

    if contents is None or len(contents) == 0:
        print("Empty file contents!  Failed to save JSON File!")
        return

    if not os.path.exists(directory_path):
        os.makedirs(directory_path)

    full_file_path = Path(directory_path) / file_name

    file_method = "a" if append_to_file else "w"

    try:
        with open(full_file_path, file_method, encoding="utf-8") as dictfile:
            json.dump(contents, dictfile, indent=4)
        print(f"JSON File successfully saved as: {full_file_path}")

    except ValueError as e:
        print(f"Error parsing Dict Contents: {e}")
    except Exception as e:
        print(f"An error occured: {e}")


def save_jsonl_file(file_name: str, contents: list[dict]) -> None:
    """Function that takes a file name, which includes the directory, and contents (dictionary) for the file then writes the results out into JSONL files that can be used for ingestion into OpenSearch.

    :param file_name: The directory location and file name of the file
        you wanted created.
    :param contents: The dictionary containing the data that will be
        parsed into a json file.

    :returns: Nothing.
    """
    # TODO: This will need to change to write the csv
    # file into an S3 bucket
    # maybe will need a service for all the S3 work?
    full_file_path = BASE_FOLDER / file_name
    try:
        with open(full_file_path, "w") as f:
            f.writelines(json.dumps(doc) + "\n" for doc in contents)
        print(f"JSONL File successfully saved as: {full_file_path}")

    except ValueError as e:
        print(f"Error parsing Dict Contents: {e}")
    except Exception as e:
        print(f"An error occured: {e}")
