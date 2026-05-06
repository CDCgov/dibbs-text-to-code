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
import os
import re



SNOINC_DIRECTORY = "./data/snoinc_extracts"
SNOINC_ENHANCEMENTS_DIRECTORY = "./data/snoinc_extracts/enhancements"
SNOINC_DELTA_DIRECTORY = "./data/snoinc_extracts/deltas"
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
