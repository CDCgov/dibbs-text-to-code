import csv
import os

import requests

# Set Terminology URLS
LOINC_BASE_URL = "https://loinc.regenstrief.org/searchapi/loincs?"
LOINC_LAB_ORDER_SUFFIX = "query=orderobs:Order+OR+orderobs:Both&count=500"
LOINC_LAB_RESULT_SUFFIX = "query=orderobs:Observation+OR+orderobs:Both&count=500"

# Get Terminology Usernames and Passwords
LOINC_USERNAME = os.environ.get("LOINC_USERNAME")
LOINC_PWD = os.environ.get("LOINC_PWD")

# CSV file settings
CSV_DIRECTORY = "assets/"


def get_loinc_lab_orders():  # noqa: D103
    api_url = LOINC_BASE_URL + LOINC_LAB_ORDER_SUFFIX
    loinc_response = requests.get(api_url, auth=(LOINC_USERNAME, LOINC_PWD))

    loinc_filename = "loinc_lab_orders.csv"

    if loinc_response.status_code != 200:
        print(
            f"ERROR Retrieving LOINC ORDER CODES: {loinc_response.status_code}: {loinc_response.text}"
        )
        return

    loinc_orders = loinc_response.json()
    loinc_order_rows = []

    record_count = loinc_orders["ResponseSummary"]["RecordsFound"]
    print(f"Record Count: {record_count}")
    current_row_count = loinc_orders["ResponseSummary"]["RowsReturned"]
    next_url_call = loinc_orders["ResponseSummary"]["Next"]

    while current_row_count > 0 or next_url_call is None:
        loinc_order_rows = process_loinc_results(loinc_orders["Results"], loinc_order_rows)

        next_loinc_response = requests.get(next_url_call, auth=(LOINC_USERNAME, LOINC_PWD))
        if next_loinc_response.status_code != 200:
            print(
                f"ERROR Retrieving LOINC ORDER CODES: {next_loinc_response.status_code}: {next_loinc_response.text}"
            )
            return
        loinc_orders = next_loinc_response.json()
        current_row_count = loinc_orders["ResponseSummary"]["RowsReturned"]
        next_url_call = loinc_orders.get("ResponseSummary").get("Next")
        if next_url_call is None:
            break

    save_valueset_csv_file(loinc_filename, loinc_order_rows)


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
    get_loinc_lab_orders()
