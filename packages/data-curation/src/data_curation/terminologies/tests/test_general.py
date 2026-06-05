import pytest

from data_curation.terminologies import general


def test_clean_text_string_empty() -> None:
    text = None
    result = general.clean_text_string(text)
    assert result == ""


def test_clean_text_string_no_space() -> None:
    text = "MY TEST"
    result = general.clean_text_string(text)
    assert result == text


def test_clean_text_string_spaces() -> None:
    text = "MY TEST"
    text_spaces = "  MY   TEST         "
    result = general.clean_text_string(text_spaces)
    assert result == text


def test_get_date_from_filename_no_date() -> None:
    file_name = "my_valuset_extract.csv"
    with pytest.raises(
        ValueError,
        match=rf"Unable to extract 8 digit date from file name: {file_name}!"):
        general.get_date_from_filename(file_name,"loinc")


def test_get_date_from_filename_no_file() -> None:
    file_name = ""
    with pytest.raises(
        ValueError,
        match=rf"Unable to extract 8 digit date from file name: {file_name}!"):
        general.get_date_from_filename(file_name,"loinc")


def test_get_date_from_filename_valid_loinc() -> None:
    file_name = "my_extract_file_20260514.csv"
    result = general.get_date_from_filename(file_name,"loinc")
    assert result == '2026-05-14'


def test_get_date_from_filename_valid_other() -> None:
    file_name = "my_extract_file_20260514.csv"
    result = general.get_date_from_filename(file_name,"")
    assert result == '20260514'


def test_get_date_from_filename_invalid_date() -> None:
    file_name = "my_extract_file_20265555.csv"
    with pytest.raises(
        ValueError):
        general.get_date_from_filename(file_name,"loinc")


def test_get_latest_extract_file_name_empty() -> None:
    with pytest.raises(
        FileNotFoundError):
        general.get_latest_extract_file_name("")


def test_get_latest_extract_file_name_none() -> None:
    result = general.get_latest_extract_file_name(None)
    assert result is None


def test_get_latest_extract_file_name_valid() -> None:
    prefix = "loinc_lab_names"
    result = general.get_latest_extract_file_name(prefix)
    assert result is not None
    assert prefix in result


def test_load_extract_file_to_dict_no_file() -> None:
    result = general.load_extract_file_to_dict("")
    assert result == {}


def test_load_extract_file_to_dict_valid() -> None:
    result = general.load_extract_file_to_dict("hl7_lab_interp_20260223.csv")
    assert result != {}


def test_save_valueset_csv_file_no_filename(capsys) -> None:
    general.save_valueset_csv_file(" ", [{"code": "123", "text": "Test"}])

    assert "No filename supplied.  Failed to save CSV file!" in capsys.readouterr().out


def test_save_valueset_csv_file_empty_contents(capsys) -> None:
    general.save_valueset_csv_file("test.csv", [])

    assert "Empty file contents!  Failed to save CSV!" in capsys.readouterr().out


def test_save_valueset_csv_file_valid(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(general, "BASE_FOLDER", tmp_path)

    general.save_valueset_csv_file("test.csv", [{"code": "123", "text": "Test"}])

    assert (tmp_path / "test.csv").read_text().splitlines() == [
        "code|text",
        "123|Test",
    ]


def test_save_valueset_csv_file_append(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(general, "BASE_FOLDER", tmp_path)
    file_path = tmp_path / "test.csv"
    file_path.write_text("code|text\n")

    general.save_valueset_csv_file("test.csv", [{"code": "123", "text": "Test"}], True)

    assert file_path.read_text().splitlines() == [
        "code|text",
        "123|Test",
    ]


def test_save_valueset_csv_file_value_error(tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.setattr(general, "BASE_FOLDER", tmp_path)

    class MockWriter:
        def __init__(self, csvfile: object, csv_headers: object, delimiter: str) -> None:
            pass

        def writeheader(self) -> None:
            pass

        def writerows(self, contents: list[dict]) -> None:
            raise ValueError("bad csv")

    monkeypatch.setattr(general.csv, "DictWriter", MockWriter)

    general.save_valueset_csv_file("test.csv", [{"code": "123", "text": "Test"}])

    assert "Error parsing Dict Contents: bad csv" in capsys.readouterr().out


def test_save_valueset_csv_file_exception(tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.setattr(general, "BASE_FOLDER", tmp_path)

    def mock_open(file: object, mode: str, newline: str, encoding: str) -> object:
        raise RuntimeError("bad open")

    monkeypatch.setattr("builtins.open", mock_open)

    general.save_valueset_csv_file("test.csv", [{"code": "123", "text": "Test"}])

    assert "An error occured: bad open" in capsys.readouterr().out


def test_save_json_file_no_filename_or_path(capsys) -> None:
    general.save_json_file("", "test.json", {"code": "123"})

    assert "No filename & path supplied.  Failed to save JSON File!" in capsys.readouterr().out


def test_save_json_file_empty_contents(tmp_path, capsys) -> None:
    general.save_json_file(tmp_path, "test.json", {})

    assert "Empty file contents!  Failed to save JSON File!" in capsys.readouterr().out


def test_save_json_file_valid(tmp_path) -> None:
    directory_path = tmp_path / "json"

    general.save_json_file(directory_path, "test.json", {"code": "123"})

    assert (directory_path / "test.json").read_text() == '{\n    "code": "123"\n}'


def test_save_json_file_append(tmp_path) -> None:
    general.save_json_file(tmp_path, "test.json", {"code": "123"}, True)

    assert (tmp_path / "test.json").read_text() == '{\n    "code": "123"\n}'


def test_save_json_file_value_error(tmp_path, monkeypatch, capsys) -> None:
    def mock_dump(contents: dict, dictfile: object, indent: int) -> None:
        raise ValueError("bad json")

    monkeypatch.setattr(general.json, "dump", mock_dump)

    general.save_json_file(tmp_path, "test.json", {"code": "123"})

    assert "Error parsing Dict Contents: bad json" in capsys.readouterr().out


def test_save_json_file_exception(tmp_path, monkeypatch, capsys) -> None:
    def mock_open(file: object, mode: str, encoding: str) -> object:
        raise RuntimeError("bad open")

    monkeypatch.setattr("builtins.open", mock_open)

    general.save_json_file(tmp_path, "test.json", {"code": "123"})

    assert "An error occured: bad open" in capsys.readouterr().out


def test_save_jsonl_file_valid(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(general, "BASE_FOLDER", tmp_path)

    general.save_jsonl_file("test.jsonl", [{"code": "123"}, {"code": "456"}])

    assert (tmp_path / "test.jsonl").read_text().splitlines() == [
        '{"code": "123"}',
        '{"code": "456"}',
    ]


def test_save_jsonl_file_value_error(tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.setattr(general, "BASE_FOLDER", tmp_path)

    class MockFile:
        def __enter__(self) -> "MockFile":
            return self

        def __exit__(self, exc_type: object, exc_value: object, traceback: object) -> None:
            return None

        def writelines(self, lines: object) -> None:
            raise ValueError("bad jsonl")

    def mock_open(file: object, mode: str) -> MockFile:
        return MockFile()

    monkeypatch.setattr("builtins.open", mock_open)

    general.save_jsonl_file("test.jsonl", [{"code": "123"}])

    assert "Error parsing Dict Contents: bad jsonl" in capsys.readouterr().out


def test_save_jsonl_file_exception(tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.setattr(general, "BASE_FOLDER", tmp_path)

    def mock_open(file: object, mode: str) -> object:
        raise RuntimeError("bad open")

    monkeypatch.setattr("builtins.open", mock_open)

    general.save_jsonl_file("test.jsonl", [{"code": "123"}])

    assert "An error occured: bad open" in capsys.readouterr().out