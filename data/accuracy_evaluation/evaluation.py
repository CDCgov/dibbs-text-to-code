import json
import os
from data.accuracy_evaluation.utils import export_json, import_json

# sample run: python data/accuracy_evaluation/evaluation.py
# could make this a sys.argv parameter or just update directly as needed, for now hardcoding
# other sample file to determine efficacy: data/accuracy_evaluation/sample_data/evaluation_results_sample_evaluation_file.json
# LOINC codes can be added to a file lacking them using add_loinc_codes.py
input_file = "data/accuracy_evaluation/sample_data/eval_results_snippet_with_loinc_codes.txt"

# Mapping files generated from build_evaluation_files.py
loinc_to_oids_file = "data/accuracy_evaluation/loinc_to_oids.txt"
oid_to_conditions_file = "data/accuracy_evaluation/oid_to_conditions.txt"


def accuracy_evaluation(
    loinc_to_oids_file: str, oid_to_conditions_file: str, input_file: str
) -> list[dict]:
    """
    Evaluates the accuracy of LOINC to OID mappings against known conditions.
    :param loinc_to_oids_file: Path to the LOINC to OIDs mapping file.
    :param oid_to_conditions_file: Path to the OID to conditions mapping file.
    :param input_file: Path to the input JSON file containing LOINC codes to evaluate.
    """
    loinc_to_oids = import_json(loinc_to_oids_file)
    oid_to_conditions = import_json(oid_to_conditions_file)
    with open(input_file, "r") as f:
        eval_data = [json.loads(line) for line in f if line.strip()]

    status_priority = {
        "first-degree match": 5,
        "second-degree match, one unique condition": 4,
        "third-degree match, one unique condition": 3,
        "third-degree match, multiple unique conditions": 2,
        "no match": 1,
        "no OIDs returned, investigate LOINC validity": 0,
        "no conditions returned, investigate OID validity": 0,
        "no LOINC returned": 0,
    }

    for item in eval_data:
        expected_loinc = item.get("expected_loinc")
        for result in item.get("results"):
            returned_loinc = result.get("loinc_code")

            returned_oids = sorted(loinc_to_oids.get(returned_loinc, []) if returned_loinc else [])
            expected_oids = sorted(loinc_to_oids.get(expected_loinc, []) if expected_loinc else [])

            returned_conditions = sorted(
                list(set(oid_to_conditions.get(oid) for oid in returned_oids))
            )
            expected_conditions = sorted(
                list(set(oid_to_conditions.get(oid) for oid in expected_oids))
            )
            if returned_loinc is None:
                status = "no LOINC returned"
            elif returned_loinc == expected_loinc:
                status = "first-degree match"
            elif returned_oids == expected_oids and len(returned_conditions) == 1:
                status = "second-degree match, one unique condition"
            elif returned_conditions == expected_conditions and len(returned_conditions) == 1:
                status = "third-degree match, one unique condition"
            elif returned_conditions == expected_conditions and len(returned_conditions) > 1:
                status = "third-degree match, multiple unique conditions"
            elif not returned_oids:
                status = "no OIDs returned, investigate LOINC validity"
            elif not returned_conditions:
                status = "no conditions returned, investigate OID validity"
            else:
                status = "no match"
            result["status"] = status

            # determine best status for the overall item (i.e., did any of the results achieve a match)
            best_status = "no match"
            if status_priority.get(status, 0) > status_priority.get(best_status, 0):
                best_status = status

            if best_status == "first-degree match":
                break

        item["status"] = best_status

    return eval_data


if __name__ == "__main__":
    results = accuracy_evaluation(loinc_to_oids_file, oid_to_conditions_file, input_file)
    input_file_name = input_file.split("/")[-1].split(".")[0]
    export_json(results, os.path.join(os.path.split(input_file)[0], f"evaluation_results_{input_file_name}.json"))
