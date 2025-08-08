import csv
import os

import requests

# Set Terminology URLS
LOINC_BASE_URL = "https://loinc.regenstrief.org/searchapi/loincs?"
LOINC_LAB_ORDER_SUFFIX = "query=orderobs:Order+OR+orderobs:Both&count=500"
LOINC_LAB_RESULT_SUFFIX = "query=orderobs:Observation+OR+orderobs:Both&count=500"
HL7_LAB_INTERP_URL = (
    "https://www.fhir.org/guides/stats2/valueset-us.nlm.vsac-2.16.840.1.113883.1.11.78.json"
)

# Get Terminology Usernames and Passwords
LOINC_USERNAME = os.environ.get("LOINC_USERNAME")
LOINC_PWD = os.environ.get("LOINC_PWD")

# CSV file settings
CSV_DIRECTORY = "assets/"


def get_hl7_lab_interp():  # noqa: D103
    hl7_filename = "hl7_lab_interp.csv"
    hl7_response = requests.get(HL7_LAB_INTERP_URL)

    if hl7_response.status_code != 200:
        print(
            f"ERROR Retrieving HL7 LAB Interpretation CODES: {hl7_response.status_code}: {hl7_response.text}"
        )
        return
    hl7_codes = hl7_response.json().get("compose").get("include")[0].get("concept")

    if hl7_codes is not None:
        record_count = hl7_response.json().get("expansion").get("total")
        print(f"HL7 Lab Interpretation Record Count: {record_count}")

        # replace 'display' key with 'text
        key_replacements = {"display": "text"}
        for hl7_row in hl7_codes:
            for old_key, new_key in key_replacements.items():
                if old_key in hl7_row:
                    hl7_row[new_key] = hl7_row[old_key]
                    del hl7_row[old_key]
        save_valueset_csv_file(hl7_filename, hl7_codes)


def get_loinc_lab_orders():  # noqa: D103
    api_url = LOINC_BASE_URL + LOINC_LAB_ORDER_SUFFIX
    loinc_filename = "loinc_lab_orders.csv"
    loinc_vs_type = "Lab Orders"
    loinc_order_rows = process_loinc_valueset(api_url, loinc_vs_type)

    save_valueset_csv_file(loinc_filename, loinc_order_rows)


def get_loinc_lab_results():  # noqa: D103
    api_url = LOINC_BASE_URL + LOINC_LAB_RESULT_SUFFIX
    loinc_filename = "loinc_lab_result.csv"
    loinc_vs_type = "Lab Results"
    loinc_result_rows = process_loinc_valueset(api_url, loinc_vs_type)

    save_valueset_csv_file(loinc_filename, loinc_result_rows)


def process_loinc_valueset(api_url, loinc_valueset_type):  # noqa: D103
    loinc_response = requests.get(api_url, auth=(LOINC_USERNAME, LOINC_PWD))
    if loinc_response.status_code != 200:
        print(
            f"ERROR Retrieving LOINC {loinc_valueset_type} CODES: {loinc_response.status_code}: {loinc_response.text}"
        )
        return

    loinc_codes = loinc_response.json()
    loinc_rows = []

    record_count = loinc_codes["ResponseSummary"]["RecordsFound"]
    print(f"{loinc_valueset_type} Record Count: {record_count}")
    current_row_count = loinc_codes["ResponseSummary"]["RowsReturned"]
    next_url_call = loinc_codes["ResponseSummary"]["Next"]

    while current_row_count > 0 or next_url_call is None:
        loinc_rows = process_loinc_results(loinc_codes["Results"], loinc_rows)

        next_loinc_response = requests.get(next_url_call, auth=(LOINC_USERNAME, LOINC_PWD))
        if next_loinc_response.status_code != 200:
            print(
                f"ERROR Retrieving LOINC {loinc_valueset_type} CODES: {next_loinc_response.status_code}: {next_loinc_response.text}"
            )
            return
        loinc_codes = next_loinc_response.json()
        current_row_count = loinc_codes["ResponseSummary"]["RowsReturned"]
        next_url_call = loinc_codes.get("ResponseSummary").get("Next")
        if next_url_call is None:
            break

    return loinc_rows


def process_loinc_results(loinc_results, loinc_order_rows) -> dict:  # noqa: D103
    if len(loinc_results) == 0:
        print("NO RESULTS TO PROCESS!")
        return loinc_order_rows

    for loinc_result in loinc_results:
        loinc_order_rows = get_all_loinc_terms_per_code(loinc_result, loinc_order_rows)

    return loinc_order_rows


def get_all_loinc_terms_per_code(loinc_result: dict, loinc_order_rows) -> dict:  # noqa: D103
    result_code = loinc_result.get("LOINC_NUM")
    if loinc_result.get("SHORTNAME") is not None:
        result_row = {"code": result_code, "text": loinc_result.get("SHORTNAME")}
        loinc_order_rows.append(result_row)
    if loinc_result.get("LONG_COMMON_NAME") is not None:
        result_row = {"code": result_code, "text": loinc_result.get("LONG_COMMON_NAME")}
        loinc_order_rows.append(result_row)

    # NOTE: There are other fields that have additional descriptions that we can pull
    #  from as well.  ie. TermDescriptions [], FormalName, and DisplayName.
    #  Will leave these out for now.

    return loinc_order_rows


def save_valueset_csv_file(filename: str, contents: dict):  # noqa: D103
    if not filename.strip():
        print("No filename supplied.  Failed to save CSV file!")
        return

    if contents is None and len(contents) == 0:
        print("Empty file contents!  Failed to save CSV!")
        return

    try:
        full_file_path = os.path.join(CSV_DIRECTORY, filename)
        csv_headers = contents[0].keys()

        with open(full_file_path, "w", newline="", encoding="utf-8") as csvfile:
            writer = csv.DictWriter(csvfile, csv_headers)
            writer.writeheader()
            writer.writerows(contents)
        print(f"CSV File successfully saved as {full_file_path}")

    except ValueError as e:
        print(f"Error parsing Dict Contents: {e}")
    except Exception as e:
        print(f"An error occured: {e}")


if __name__ == "__main__":
    # get_loinc_lab_orders()
    # get_loinc_lab_results()
    get_hl7_lab_interp()
