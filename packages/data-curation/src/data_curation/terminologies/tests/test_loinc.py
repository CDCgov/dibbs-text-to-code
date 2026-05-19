from pathlib import Path
from data_curation.terminologies.loinc import _create_embedding_record, _create_embedding_records

API_RESPONSE_DIRECTORY = Path(__file__).parent / "assets"
LOINC_LAB_RESPONSE = API_RESPONSE_DIRECTORY / "loinc_lab_response.json"
EXISTING_LOINC_FILE = API_RESPONSE_DIRECTORY / "loinc_lab_names_20260223.csv"

def test_create_embedding_record() -> None:
    loinc_code = "12345-F"
    loinc_term = "TEST NAME"
    loinc_axis = {}
    loinc_axis["loinc_code"] = loinc_code
    loinc_axis["loinc_type"] = "Both"
    loinc_axis["property"] = "TEST PROPERTY"
    loinc_axis["time"] = "TEST TIME"
    loinc_axis["system"] = "TEST SYSTEM"
    loinc_axis["scale"] = "TEST SCALE"
    loinc_axis["method"] = "TEST METHOD"
    loinc_axis["class"] = "TEST CLASS"
    loinc_term_type = "TEST TERM"
    expected = {
        "id": 140,
        "description": "TEST NAME",
        "description_vector": [],
        "loinc_type": "Both",
        "loinc_code": "12345-F",
        "loinc_name_type": "TEST TERM",
        "property": "TEST PROPERTY",
        "time_aspect": "TEST TIME",
        "system": "TEST SYSTEM",
        "scale_type": "TEST SCALE",
        "method_type": "TEST METHOD",
        "class_type": "TEST CLASS"
    }
    result = _create_embedding_record(140,loinc_term,loinc_term_type,loinc_axis)    
    assert result == expected

def test_create_embedding_records() -> None:
    loinc_id1 = 155
    loinc_code = "12345-F"
    loinc_axis = {}
    loinc_axis["loinc_code"] = loinc_code
    loinc_axis["loinc_type"] = "Both"
    loinc_axis["property"] = "TEST PROPERTY"
    loinc_axis["time"] = "TEST TIME"
    loinc_axis["system"] = "TEST SYSTEM"
    loinc_axis["scale"] = "TEST SCALE"
    loinc_axis["method"] = "TEST METHOD"
    loinc_axis["class"] = "TEST CLASS"
    changes = ["short_name","long_name"]

    # loinc row return from our process that organizes
    # data from LOINC API call
    loinc_row = {}
    loinc_row["short_name"] = "TEST NAME"
    loinc_row["long_name"] = "ANOTHER TEST NAME"
    loinc_row["display_name"] = "TEST DISPLAY"
    loinc_row["full_name"] = "TEST FULL NAME"
    loinc_row["consumer_name"] = "TEST CONSUMER NAME"
    loinc_row["lab_type"] = loinc_axis["loinc_type"]
    loinc_row["property"] = loinc_axis["property"]
    loinc_row["time_aspect"] = loinc_axis["time"]
    loinc_row["system"] = loinc_axis["system"]
    loinc_row["scale_type"] = loinc_axis["scale"]
    loinc_row["method_type"] = loinc_axis["method"]
    loinc_row["class_type"] = loinc_axis["class"]

    record_1 = {
        "id": 156,
        "description": "TEST NAME",
        "description_vector": [],
        "loinc_type": loinc_axis["loinc_type"],
        "loinc_code": loinc_axis["loinc_code"],
        "loinc_name_type": "short_name",
        "property": loinc_axis["property"],
        "time_aspect":loinc_axis["time"],
        "system": loinc_axis["system"],
        "scale_type": loinc_axis["scale"],
        "method_type": loinc_axis["method"],
        "class_type": loinc_axis["class"]
    }
    record_2 = {
        "id": 157,
        "description": "ANOTHER TEST NAME",
        "description_vector": [],
        "loinc_type": loinc_axis["loinc_type"],
        "loinc_code": loinc_axis["loinc_code"],
        "loinc_name_type": "long_name",
        "property": loinc_axis["property"],
        "time_aspect":loinc_axis["time"],
        "system": loinc_axis["system"],
        "scale_type": loinc_axis["scale"],
        "method_type": loinc_axis["method"],
        "class_type": loinc_axis["class"]
    }
    expected = [record_1,record_2]
    result = _create_embedding_records(loinc_id1,loinc_code,loinc_row,changes)
    assert result == expected