#!/usr/bin/env python

"""
data_curation.terminologies.utils.hl7
~~~~~~~~~~~~~~~~~~~~~~~~~

This module contains a number of helper functions designed to assist
with the process of extracting HL7 Specific codes and their terms 
to generate and maintain embeddings in Opensearch for TTC.
"""
import sys
import requests
from .general import clean_text_string

# Set Terminology URLS
HL7_LAB_INTERP_URL = (
    "https://terminology.hl7.org/2.1.0/CodeSystem-v3-ObservationInterpretation.json"
)
HL7_ENCOUNTER_CODE_URL = "https://terminology.hl7.org/6.5.0/CodeSystem-v3-ActCode.json"


def get_hl7_encounter_act_codes() -> list[dict]:
    """Function to get all the HL7 Codes and Terms for 
        Encounter Act via the HL7 Valueset CodeSystem JSON file
        and organize the data into a list of dictionaries.

        :returns: A list of dictionaries containing HL7 Encounter
            Act records including codes, text, and descriptions.
    """
    hl7_response = requests.get(HL7_ENCOUNTER_CODE_URL)
    encounter_act_code = "_ActEncounterCode"
    hl7_rows = []

    if hl7_response.status_code != 200:
        # TODO: In Subsequent PR update this to be a logging statement
        print(
            f"ERROR Retrieving HL7 Encounter Act Codes: {hl7_response.status_code}: {hl7_response.text}",
            file=sys.stderr,
        )
        sys.exit(1)
    hl7_codes = hl7_response.json().get("concept")

    if hl7_codes is not None:
        record_count = len(hl7_codes)
        # TODO: In Subsequent PR update this to be a logging statement
        print(f"HL7 ACT Codes to process through to get the Encounter Codes: {record_count}")

        for hl7_row in hl7_codes:
            hl7_code = hl7_row.get("code")
            hl7_text = hl7_row.get("display")
            hl7_definition = hl7_row.get("definition")

            # get list of properties and ensure that the code/name is part
            # of the specific Encounter Act Code Subset
            hl7_properties = hl7_row.get("property")

            for property in hl7_properties:
                property_code = property.get("code")
                property_value = property.get("valueCode")

                if (
                    property_code
                    and property_code == "subsumedBy"
                    and property_value
                    and property_value == encounter_act_code
                ):
                    result_row = {
                        "code": hl7_code,
                        "text": clean_text_string(hl7_text),
                    }
                    result_row["description"] = clean_text_string(hl7_definition)
                    hl7_rows.append(result_row)
        # Hard coded external encounter
        # This is the specified code, based upon the eICR specificiation, if an encounter is
        # not associated with a specific 'patient visit'. You use the PHC2237 code for "External Encounter"
        # in an eICR when a public health trigger occurs outside of a specific patient encounter,
        # meaning it is not related to a particular visit or hospitalization
        external_encounter = {
            "code": "PHC2237",
            "text": "External Encounter",
            "description": "External Encounter",
        }
        hl7_rows.append(external_encounter)
        # TODO: In Subsequent PR update this to be a logging statement
        print(f"HL7 Encounter Act Codes Retrieved from HL7 Act Codes: {len(hl7_rows)}")
        return hl7_rows


def get_hl7_lab_interp() -> list[dict]:
    """Function to get all the HL7 Codes and Terms for 
        Lab Interpretations via the HL7 Valueset CodeSystem JSON file
        and organize the data into a list of dictionaries.

        :returns: A list of dictionaries containing HL7 Lab
            Interpretations records including codes and text.
    """
    hl7_response = requests.get(HL7_LAB_INTERP_URL)
    hl7_rows = []

    if hl7_response.status_code != 200:
        # TODO: In Subsequent PR update this to be a logging statement
        print(
            f"ERROR Retrieving HL7 LAB Interpretation CODES: {hl7_response.status_code}: {hl7_response.text}",
            file=sys.stderr,
        )
        sys.exit(1)
    hl7_codes = hl7_response.json().get("concept")

    if hl7_codes is not None:
        record_count = len(hl7_codes)
        # TODO: In Subsequent PR update this to be a logging statement
        print(f"HL7 Lab Interpretation Record Count: {record_count}")

        for hl7_row in hl7_codes:
            hl7_code = hl7_row.get("code")
            hl7_text = hl7_row.get("display")
            # NOTE: we can add back in the definition as description, but there are some
            # special character filtering we may need to do and some of the
            # data in this field could clutter things up
            # hl7_desc = hl7_row.get("definition")
            if (
                hl7_code
                and not hl7_code.startswith(("_", "Observation", "OBX", "ReactivityObs"))
                and hl7_text
            ):
                result_row = {
                    "code": hl7_code,
                    "text": clean_text_string(hl7_text),
                }
                hl7_rows.append(result_row)
    return hl7_rows
