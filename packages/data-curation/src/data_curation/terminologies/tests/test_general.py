import pytest

from data_curation.terminologies.general import clean_text_string, get_date_from_filename, get_latest_extract_file_name, load_extract_file_to_dict

def test_clean_text_string_empty() -> None:
    text = None
    result = clean_text_string(text)
    assert result == ""


def test_clean_text_string_no_space() -> None:
    text = "MY TEST"
    result = clean_text_string(text)
    assert result == text


def test_clean_text_string_spaces() -> None:
    text = "MY TEST"
    text_spaces = "  MY   TEST         "
    result = clean_text_string(text_spaces)
    assert result == text


def test_get_date_from_filename_no_date() -> None:
    file_name = "my_valuset_extract.csv"
    with pytest.raises(
        ValueError,
        match=rf"Unable to extract 8 digit date from file name: {file_name}!"):
        get_date_from_filename(file_name,"loinc")


def test_get_date_from_filename_no_file() -> None:
    file_name = ""
    with pytest.raises(
        ValueError,
        match=rf"Unable to extract 8 digit date from file name: {file_name}!"):
        get_date_from_filename(file_name,"loinc")


def test_get_date_from_filename_valid_loinc() -> None:
    file_name = "my_extract_file_20260514.csv"
    result = get_date_from_filename(file_name,"loinc")
    assert result == '2026-05-14'


def test_get_date_from_filename_valid_other() -> None:
    file_name = "my_extract_file_20260514.csv"
    result = get_date_from_filename(file_name,"")
    assert result == '20260514'


def test_get_date_from_filename_invalid_date() -> None:
    file_name = "my_extract_file_20265555.csv"
    with pytest.raises(
        ValueError):
        get_date_from_filename(file_name,"loinc")


def test_get_latest_extract_file_name_empty() -> None:
    with pytest.raises(
        FileNotFoundError):
        get_latest_extract_file_name("")


def test_get_latest_extract_file_name_none() -> None:
    result = get_latest_extract_file_name(None)
    assert result is None


def test_get_latest_extract_file_name_valid() -> None:
    prefix = "loinc_lab_names"
    result = get_latest_extract_file_name(prefix)
    assert result is not None
    assert prefix in result


def test_load_extract_file_to_dict_no_file() -> None:
    result = load_extract_file_to_dict("")
    assert result == {}


def test_load_extract_file_to_dict_valid() -> None:
    result = load_extract_file_to_dict("hl7_lab_interp_20260223.csv")
    assert result != {}


