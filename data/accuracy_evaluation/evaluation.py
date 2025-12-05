import json


def import_json(file_path: str) -> dict:
    """
    Imports a JSON file and returns its content as a dictionary.
    :param file_path: Path to the JSON file.
    """
    with open(file_path, "r") as f:
        data = json.load(f)
    return data


loinc_to_oids_file = "data/accuracy_evaluation/loinc_to_oids.txt"
oid_to_conditions_file = "data/accuracy_evaluation/oid_to_conditions.txt"
input_file = "data/accuracy_evaluation/sample_evaluation_file.txt"


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
    eval_data = import_json(input_file)
    results = []

    for item in eval_data:
        returned_loinc = item.get("returned_loinc")
        expected_loinc = item.get("expected_loinc")

        returned_oids = sorted(loinc_to_oids.get(returned_loinc, []) if returned_loinc else [])
        expected_oids = sorted(loinc_to_oids.get(expected_loinc, []) if expected_loinc else [])

        returned_conditions = sorted(list(set(oid_to_conditions.get(oid) for oid in returned_oids)))
        expected_conditions = sorted(list(set(oid_to_conditions.get(oid) for oid in expected_oids)))

        if returned_loinc == expected_loinc and returned_loinc is not None:
            status = "first-degree match"
        elif returned_oids == expected_oids and returned_oids:
            status = "second-degree match"
        elif returned_conditions == expected_conditions and len(returned_conditions) == 1:
            status = "third-degree match, one unique condition"
        elif returned_conditions == expected_conditions and len(returned_conditions) > 1:
            status = "third-degree match, multiple unique conditions"
        else:
            status = "no match"

        result_item = dict(item)
        result_item["status"] = status
        results.append(result_item)

    return results


if __name__ == "__main__":
    results = accuracy_evaluation(loinc_to_oids_file, oid_to_conditions_file, input_file)
    with open("data/accuracy_evaluation/evaluation_results.json", "w") as f:
        json.dump(results, f, indent=2)
