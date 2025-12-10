import csv
import os

script_dir = os.path.dirname(os.path.abspath(__file__))
os.chdir(script_dir)

SNOINC_CODE_TYPE_FILE = "loinc_lab_names_20251107.csv"
RESULTS_FILE = "loinc_lab_names_null_values.txt"

empty_loinc_descriptions = []
total_count = 0

# get the loinc lab codes and types into a dictionary list for use
# later instead of reading through this file for each embedding file
with open(SNOINC_CODE_TYPE_FILE, encoding="utf-8") as file:
    csv_reader = csv.reader(file, delimiter="|")
    # Optionally skip the header row
    header = next(csv_reader)
    print(f"HEADER: {header}")
    null_embeddings = 0

    for row in csv_reader:
        code = row[0]
        disp = row[4]
        long_name = row[3]
        short_name = row[2]
        null_fields = []

        if disp is None or disp == "":
            null_fields.append("DISPLAY NAME")
            null_embeddings += 1

        if long_name is None or long_name == "":
            null_fields.append("LONG NAME")
            null_embeddings += 1

        if short_name is None or short_name == "":
            null_fields.append("SHORT NAME")
            null_embeddings += 1

        if len(null_fields) > 0:
            total_count += 1
            # null_embeddings += len(null_fields)
            null_rec = f"{code}|{long_name}|NULL FIELDS: {','.join(null_fields)}"
            empty_loinc_descriptions.append(null_rec)
    empty_loinc_descriptions.insert(
        0,
        f"TOTAL LOINC CODES WITH NULL TEXT OF SOME TYPE: {total_count}",
    )
    empty_loinc_descriptions.insert(0, f"TOTAL EMBEDDINGS WITH NULL TEXT: {null_embeddings}")


with open(RESULTS_FILE, "w") as file:
    for row in empty_loinc_descriptions:
        file.write(row + "\n")
