from utils import export_json
from utils import import_json

# sample run: python data/accuracy_evaluation/evaluation.py
# could make this a sys.argv parameter or just update directly as needed, for now hardcoding
input_file = "data/accuracy_evaluation/eval_results_snippet_with_codes.txt"


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
    eval_data = import_json(input_file)
    results = []

    for item in eval_data:
        returned_loinc = item.get("returned_loinc")
        expected_loinc = item.get("expected_loinc")

        returned_oids = sorted(loinc_to_oids.get(returned_loinc, []) if returned_loinc else [])
        expected_oids = sorted(loinc_to_oids.get(expected_loinc, []) if expected_loinc else [])

        returned_conditions = sorted(list(set(oid_to_conditions.get(oid) for oid in returned_oids)))
        expected_conditions = sorted(list(set(oid_to_conditions.get(oid) for oid in expected_oids)))

        print(
            f"Evaluating LOINC:\n"
            f"returned LOINC: {returned_loinc}\n"
            f"expected LOINC: {expected_loinc}\n"
            f"returned OIDs: {returned_oids}\n"
            f"expected OIDs: {expected_oids}\n"
            f"returned conditions: {returned_conditions}\n"
            f"expected conditions: {expected_conditions}\n"
        )
        if returned_loinc is None:
            status = "no LOINC returned"
        elif returned_oids is None:
            status = "no OIDs returned, investigate LOINC validity"
        elif returned_conditions is None:
            status = "no conditions returned, investigate OID validity"
        elif returned_loinc == expected_loinc:
            status = "first-degree match"
        elif returned_oids == expected_oids and len(returned_conditions) == 1:
            status = "second-degree match, one unique condition"
        elif returned_conditions == expected_conditions and len(returned_conditions) == 1:
            status = "third-degree match, one unique condition"
        elif returned_conditions == expected_conditions and len(returned_conditions) > 1:
            status = "third-degree match, multiple unique conditions"
        else:
            status = "no match"
        print(f"Status: {status}")
        print("-----")

        result_item = dict(item)
        result_item["status"] = status
        results.append(result_item)

    return results


if __name__ == "__main__":
    results = accuracy_evaluation(loinc_to_oids_file, oid_to_conditions_file, input_file)
    input_file_name = input_file.split("/")[-1].split(".")[0]
    export_json(results, f"data/accuracy_evaluation/evaluation_results_{input_file_name}.json")
