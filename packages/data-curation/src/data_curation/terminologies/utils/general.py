#!/usr/bin/env python"""

"""
data_curation.terminologies.utils.general
~~~~~~~~~~~~~~~~~~~~~~~~~

This module contains a number of helper functions designed to assist
with the process of extracting Medical Terminology codes and their terms 
to generate and maintain embeddings in Opensearch for TTC.
"""

# File & Directories
import os
import re
from utils import regex_patterns


SNOINC_DIRECTORY = "./data/snoinc_extracts"
SNOINC_ENHANCEMENTS_DIRECTORY = "./data/snoinc_extracts/enhancements"
SNOINC_DELTA_DIRECTORY = "./data/snoinc_extracts/deltas"
TMP_DIRECTORY = "./tmp"

UMLS_API_KEY = os.environ.get("UMLS_API_KEY")


def clean_text_string(value: str) -> str:
    if value is not None:
        return re.sub(regex_patterns.MULTIPLE_SPACE, " ", value).strip()
    else:
        return ""