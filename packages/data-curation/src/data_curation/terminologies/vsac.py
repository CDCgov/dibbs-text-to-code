#!/usr/bin/env python

"""data_curation.terminologies.utils.vsac
~~~~~~~~~~~~~~~~~~~~~~~~~

This module contains a number of helper functions designed to assist
with the process of extracting The Value Set Authority Center (VSAC)
codes and their terms to generate and maintain embeddings in Opensearch for TTC.
"""

import requests

from .general import UMLS_API_KEY, clean_text_string

# Terminology URLS
VSAC_MEDICATIONS_URL = "https://cts.nlm.nih.gov/fhir/ValueSet/2.16.840.1.113762.1.4.1010.4/$expand"
VSAC_VACCINES_URL = "https://cts.nlm.nih.gov/fhir/ValueSet/2.16.840.1.113762.1.4.1010.6/$expand"
VSAC_PROBLEMS_URL = (
    "https://cts.nlm.nih.gov/fhir/ValueSet/2.16.840.1.113883.3.88.12.3221.7.4/$expand"
)


def get_vsac_rxnorm_medications() -> list[dict]:
    """Function to get the all VSAC RXNorm Codes and terms for medications
    via the NLM/NIH VSAC API. There is an underlying function that
    processes the results from various VSAC API results into a
    common structure that is leveraged within this function.

    :returns: A list of dictionaries containing RXNorm Medication records
        including codes and text.
    """
    return process_vsac_codes(VSAC_MEDICATIONS_URL, "RXNORM Medications")


def get_vsac_cvx_vaccines() -> list[dict]:
    """Function to get the all VSAC CVX Codes and terms for administered
    vaccines via the NLM/NIH VSAC API.  There is an underlying
    function that processes the results from various VSAC API
    results into a common structure that is leveraged within this function.

    :returns: A list of dictionaries containing RXNorm Medication records
        including codes and text.
    """
    return process_vsac_codes(VSAC_VACCINES_URL, "CVX Vaccines")


# problems are also known as "Diagnosis/Symptom Codes"
def get_vsac_snomed_problems() -> list[dict]:
    """Function to get the all VSAC SNOMED Codes and terms for
    Diagnosis/Problems via the NLM/NIH VSAC API. There is an
    underlying function that processes the results from various
    VSAC API results into a common structure that is leveraged
    within this function.

    :returns: A list of dictionaries containing SNOMED Problem records
        including codes and text.
    """
    return process_vsac_codes(VSAC_PROBLEMS_URL, "SNOMED Problems (Diagnosis/Symptoms)")


def process_vsac_codes(api_url: str, vs_type: str) -> list[dict]:
    """Process to obtain VSAC API results for various value sets
    and organize them into a common structure that is leveraged
    by other functions within this module.

    :returns: A list of dictionaries containing different value set records
        including codes and text.
    """
    if UMLS_API_KEY is None:
        raise KeyError("UMLS_API_KEY Environment Variable must be set to a proper UMLS API Key!")

    record_offset = 0
    params = {"offset": record_offset}
    vsac_response = requests.get(api_url, params=params, auth=("apikey", UMLS_API_KEY))
    record_count = 0
    total_records = 1
    data_rows = []

    while vsac_response.status_code == 200 and record_count < total_records:
        # get the offset and record counts from the 'expansion'
        vsac_expansion = vsac_response.json().get("expansion")
        if vsac_expansion:
            if total_records == 1:
                total_records = vsac_expansion.get("total")
                # TODO: In Subsequent PR update this to be a logging statement
                print(f"Total {vs_type} to be processed: {total_records}")
            count_params = vsac_expansion.get("parameter")
            for vs_param in count_params:
                if vs_param.get("name") and vs_param.get("name") == "count":
                    record_count += vs_param.get("valueInteger")

            # get all the codes for the valueset
            vs_codes = vsac_expansion.get("contains")

            for vs_code in vs_codes:
                code = vs_code.get("code")
                text = vs_code.get("display")

                if code and text:
                    result_row = {
                        "code": code,
                        "text": clean_text_string(text),
                    }
                    data_rows.append(result_row)

        if total_records != record_count:
            params = {"offset": record_count}
            vsac_response = requests.get(api_url, params=params, auth=("apikey", UMLS_API_KEY))
    # TODO: In Subsequent PR update this to be a logging statement
    print(f"{len(data_rows)} Codes Extracted")
    return data_rows
