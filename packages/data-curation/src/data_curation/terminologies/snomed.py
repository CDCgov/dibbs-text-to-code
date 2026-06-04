#!/usr/bin/env python

"""This module contains a number of helper functions designed to assis with the process of extracting SNOMED codes and their term to generate and maintain embeddings in Opensearch for TTC."""

import requests

from .general import UMLS_API_KEY, clean_text_string

# Terminology URLS
UMLS_SNOMED_LAB_VALUES_URL = (
    "https://uts-ws.nlm.nih.gov/rest/content/current/source/SNOMEDCT_US/260245000/descendants"
)


def get_umls_snomed_lab_values() -> list[dict]:
    """Process to get the all SNOMED Codes and terms for lab values via the UMLS API.

    :returns: A list of dictionaries containing SNOMED Lab Value records
        including codes and text.
    """
    if UMLS_API_KEY is None:
        raise KeyError("UMLS_API_KEY Environment Variable must be set to a proper UMLS API Key!")
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
                result_row = {
                    "code": snomed_code,
                    "text": clean_text_string(snomed_text),
                }
                snomed_rows.append(result_row)
                snomed_row_count += 1

        page_num += 1
        params = {"apiKey": UMLS_API_KEY, "pageNumber": page_num, "pageSize": page_size}
        umls_response = requests.get(UMLS_SNOMED_LAB_VALUES_URL, params=params)

    # TODO: In Subsequent PR update this to be a logging statement
    print(f"{snomed_row_count} Codes Extracted")
    return snomed_rows
