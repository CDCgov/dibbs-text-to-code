# bash_json_loader.py
#
# Simple python helper script to load and unpack a nested JSON file so that
# sub-keys in an array can be passed as test case values to the bash script.

import json
import os

if __name__ == "__main__":
    with open(os.environ["JSON_FP"]) as fp:
        data = json.load(fp)
    for i in data["test_cases"]:
        print(
            i["nonstandard_in"]
            + "\t"
            + i["correct_standardized_code"]
            + "\t"
            + i["numeric_loinc_code"]
        )
