import json
from pathlib import Path

import pytest

from data_curation.terminologies import loinc

API_RESPONSE_DIRECTORY = Path(__file__).parent / "assets"
LOINC_LAB_RESPONSE = API_RESPONSE_DIRECTORY / "loinc_lab_response.json"
EXISTING_LOINC_FILE = API_RESPONSE_DIRECTORY / "loinc_lab_names_20260223.csv"


class MockResponse:
    def __init__(self, status_code: int, payload: dict[str, object], text: str = "") -> None:
        """Initialize mock response."""
        self.status_code = status_code
        self.payload = payload
        self.text = text

    def json(self) -> dict[str, object]:
        return self.payload


def _loinc_result(
    code: str = "12345-F",
    short_name: str = "TEST SHORT NAME",
    long_name: str = "TEST LONG NAME",
    display_name: str = "TEST DISPLAY",
    full_name: str = "TEST FULL NAME",
    consumer_name: str = "TEST CONSUMER NAME",
    lab_type: str = "Both",
) -> dict[str, str]:
    return {
        "LOINC_NUM": code,
        "DisplayName": display_name,
        "RELATEDNAMES2": "TEST RELATED NAMES",
        "DefinitionDescription": "TEST DEFINITION",
        "ORDER_OBS": lab_type,
        "FormalName": full_name,
        "PROPERTY": "TEST PROPERTY",
        "TIME_ASPCT": "TEST TIME",
        "SYSTEM": "TEST SYSTEM",
        "SCALE_TYP": "TEST SCALE",
        "METHOD_TYP": "TEST METHOD",
        "CLASS": "TEST CLASS",
        "SHORTNAME": short_name,
        "LONG_COMMON_NAME": long_name,
        "consumer_name": consumer_name,
    }


def _loinc_row(
    code: str = "12345-F",
    short_name: str = "TEST SHORT NAME",
    long_name: str = "TEST LONG NAME",
    display_name: str = "TEST DISPLAY",
    full_name: str = "TEST FULL NAME",
    consumer_name: str = "TEST CONSUMER NAME",
    lab_type: str = "Both",
) -> dict[str, str]:
    return {
        "code": code,
        "short_name": short_name,
        "long_name": long_name,
        "display_name": display_name,
        "full_name": full_name,
        "consumer_name": consumer_name,
        "lab_type": lab_type,
        "property": "TEST PROPERTY",
        "time_aspect": "TEST TIME",
        "system": "TEST SYSTEM",
        "scale_type": "TEST SCALE",
        "method_type": "TEST METHOD",
        "class_type": "TEST CLASS",
    }


def test_extract_full_loinc_lab_names(monkeypatch: pytest.MonkeyPatch) -> None:
    rows = [_loinc_row()]

    def mock_get_loinc_lab_names(
        version: str = "", include_consumer_names: bool = False
    ) -> list[dict[str, str]]:
        return rows

    monkeypatch.setattr(loinc, "_get_loinc_lab_names", mock_get_loinc_lab_names)

    result = loinc.extract_full_loinc_lab_names(include_consumer_names=True)

    assert len(result) == 1
    assert result[0].get("code") == "12345-F"
    assert result[0].get("class_type") == "TEST CLASS"


def test_extract_full_loinc_lab_names_handles_empty_api_results(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    payload: dict[str, object] = {
        "ResponseSummary": {
            "RecordsFound": 0,
            "RowsReturned": 1,
            "Next": None,
        },
        "Results": [],
    }
    consumer_names_file = tmp_path / "consumer_names.csv"
    consumer_names_file.write_text(
        "LoincNumber|ConsumerName\n",
        encoding="utf-8",
    )

    def mock_get_with_timeout(
        api_url: str,
        auth: tuple[str, str] | None = None,
    ) -> MockResponse:
        return MockResponse(200, payload)

    monkeypatch.setattr(loinc, "LOINC_USERNAME", "username")
    monkeypatch.setattr(loinc, "LOINC_PWD", "password")
    monkeypatch.setattr(loinc, "get_with_timeout", mock_get_with_timeout)

    with pytest.raises(RuntimeError, match=r"NO RESULTS TO PROCESS!"):
        loinc.extract_full_loinc_lab_names()


def test_extract_full_loinc_lab_orders(monkeypatch: pytest.MonkeyPatch) -> None:
    rows = [_loinc_row()]

    def mock_get_loinc_lab_orders(include_consumer_names: bool = False) -> list[dict[str, str]]:
        return rows

    monkeypatch.setattr(loinc, "_get_loinc_lab_orders", mock_get_loinc_lab_orders)

    results = loinc.extract_full_loinc_lab_orders(include_consumer_names=True)

    assert len(results) == 1
    assert results[0].get("code") == "12345-F"
    assert results[0].get("consumer_name") == "TEST CONSUMER NAME"


def test_extract_full_loinc_lab_results(monkeypatch: pytest.MonkeyPatch) -> None:
    rows = [_loinc_row()]

    def mock_get_loinc_lab_results(include_consumer_names: bool = False) -> list[dict[str, str]]:
        return rows

    monkeypatch.setattr(loinc, "_get_loinc_lab_results", mock_get_loinc_lab_results)

    results = loinc.extract_full_loinc_lab_results(include_consumer_names=True)

    assert len(results) == 1
    assert results[0].get("code") == "12345-F"
    assert results[0].get("consumer_name") == "TEST CONSUMER NAME"


def test_get_loinc_lab_names(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: dict[str, str] = {}
    rows = [_loinc_row()]

    def mock_process_loinc_valueset(api_url: str, loinc_vs_type: str) -> list[dict[str, str]]:
        calls["api_url"] = api_url
        calls["loinc_vs_type"] = loinc_vs_type
        return rows

    def mock_get_loinc_consumer_names(loinc_rows: list[dict[str, str]]) -> list[dict[str, str]]:
        return loinc_rows

    monkeypatch.setattr(loinc, "_process_loinc_valueset", mock_process_loinc_valueset)
    monkeypatch.setattr(loinc, "_get_loinc_consumer_names", mock_get_loinc_consumer_names)

    result = loinc._get_loinc_lab_names("2.80", True)

    assert result == rows
    assert calls["loinc_vs_type"] == "Lab Names"
    assert "versionlastchanged:2.80" in calls["api_url"]


def test_get_loinc_lab_names_without_version(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: dict[str, str] = {}
    rows = [_loinc_row()]

    def mock_process_loinc_valueset(api_url: str, loinc_vs_type: str) -> list[dict[str, str]]:
        calls["api_url"] = api_url
        calls["loinc_vs_type"] = loinc_vs_type
        return rows

    def mock_get_loinc_consumer_names(loinc_rows: list[dict[str, str]]) -> list[dict[str, str]]:
        return loinc_rows

    monkeypatch.setattr(loinc, "_process_loinc_valueset", mock_process_loinc_valueset)
    monkeypatch.setattr(loinc, "_get_loinc_consumer_names", mock_get_loinc_consumer_names)

    result = loinc._get_loinc_lab_names(include_consumer_names=True)

    assert result == rows
    assert calls["loinc_vs_type"] == "Lab Names"
    assert calls["api_url"] == loinc.LOINC_BASE_URL + f"query={loinc.LOINC_LAB_NAMES_QUERY}"


def test_get_loinc_lab_orders(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: dict[str, str] = {}
    rows = [_loinc_row()]

    def mock_process_loinc_valueset(api_url: str, loinc_vs_type: str) -> list[dict[str, str]]:
        calls["api_url"] = api_url
        calls["loinc_vs_type"] = loinc_vs_type
        return rows

    def mock_get_loinc_consumer_names(loinc_rows: list[dict[str, str]]) -> list[dict[str, str]]:
        return loinc_rows

    monkeypatch.setattr(loinc, "_process_loinc_valueset", mock_process_loinc_valueset)
    monkeypatch.setattr(loinc, "_get_loinc_consumer_names", mock_get_loinc_consumer_names)

    result = loinc._get_loinc_lab_orders()

    assert result == rows
    assert calls["loinc_vs_type"] == "Lab Orders"
    assert calls["api_url"] == loinc.LOINC_BASE_URL + f"query={loinc.LOINC_LAB_ORDER_QUERY}"


def test_get_loinc_lab_orders_with_version(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: dict[str, str] = {}
    rows = [_loinc_row()]

    def mock_process_loinc_valueset(api_url: str, loinc_vs_type: str) -> list[dict[str, str]]:
        calls["api_url"] = api_url
        calls["loinc_vs_type"] = loinc_vs_type
        return rows

    def mock_get_loinc_consumer_names(loinc_rows: list[dict[str, str]]) -> list[dict[str, str]]:
        return loinc_rows

    monkeypatch.setattr(loinc, "_process_loinc_valueset", mock_process_loinc_valueset)
    monkeypatch.setattr(loinc, "_get_loinc_consumer_names", mock_get_loinc_consumer_names)

    result = loinc._get_loinc_lab_orders("2.80")

    assert result == rows
    assert calls["loinc_vs_type"] == "Lab Orders"
    assert "versionlastchanged:2.80" in calls["api_url"]


def test_get_loinc_lab_results(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: dict[str, str] = {}
    rows = [_loinc_row()]

    def mock_process_loinc_valueset(api_url: str, loinc_vs_type: str) -> list[dict[str, str]]:
        calls["api_url"] = api_url
        calls["loinc_vs_type"] = loinc_vs_type
        return rows

    def mock_get_loinc_consumer_names(loinc_rows: list[dict[str, str]]) -> list[dict[str, str]]:
        return loinc_rows

    monkeypatch.setattr(loinc, "_process_loinc_valueset", mock_process_loinc_valueset)
    monkeypatch.setattr(loinc, "_get_loinc_consumer_names", mock_get_loinc_consumer_names)

    result = loinc._get_loinc_lab_results()

    assert result == rows
    assert calls["loinc_vs_type"] == "Lab Results"
    assert calls["api_url"] == loinc.LOINC_BASE_URL + f"query={loinc.LOINC_LAB_RESULT_QUERY}"


def test_get_loinc_lab_results_with_version(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: dict[str, str] = {}
    rows = [_loinc_row()]

    def mock_process_loinc_valueset(api_url: str, loinc_vs_type: str) -> list[dict[str, str]]:
        calls["api_url"] = api_url
        calls["loinc_vs_type"] = loinc_vs_type
        return rows

    def mock_get_loinc_consumer_names(loinc_rows: list[dict[str, str]]) -> list[dict[str, str]]:
        return loinc_rows

    monkeypatch.setattr(loinc, "_process_loinc_valueset", mock_process_loinc_valueset)
    monkeypatch.setattr(loinc, "_get_loinc_consumer_names", mock_get_loinc_consumer_names)

    result = loinc._get_loinc_lab_results("2.80")

    assert result == rows
    assert calls["loinc_vs_type"] == "Lab Results"
    assert "versionlastchanged:2.80" in calls["api_url"]


def test_process_loinc_valueset(monkeypatch: pytest.MonkeyPatch, mocker) -> None:
    payload: dict[str, object] = {
        "ResponseSummary": {
            "RecordsFound": 1,
            "RowsReturned": 1,
            "Next": None,
        },
        "Results": [_loinc_result()],
    }

    monkeypatch.setattr(loinc, "LOINC_USERNAME", "username")
    monkeypatch.setattr(loinc, "LOINC_PWD", "password")
    mocker.patch(
        "data_curation.terminologies.loinc.get_with_timeout",
        return_value=MockResponse(200, payload),
    )

    result = loinc._process_loinc_valueset("https://example.com", "Lab Names")

    assert result == [
        {
            "code": "12345-F",
            "display_name": "TEST DISPLAY",
            "related_names": "TEST RELATED NAMES",
            "definition_desc": "TEST DEFINITION",
            "lab_type": "Both",
            "full_name": "TEST FULL NAME",
            "property": "TEST PROPERTY",
            "time_aspect": "TEST TIME",
            "system": "TEST SYSTEM",
            "scale_type": "TEST SCALE",
            "method_type": "TEST METHOD",
            "class_type": "TEST CLASS",
            "short_name": "TEST SHORT NAME",
            "long_name": "TEST LONG NAME",
        }
    ]


def test_process_loinc_valueset_gets_next_page(monkeypatch: pytest.MonkeyPatch, mocker) -> None:
    first_payload: dict[str, object] = {
        "ResponseSummary": {
            "RecordsFound": 2,
            "RowsReturned": 1,
            "Next": "https://example.com/next",
        },
        "Results": [_loinc_result(code="12345-F")],
    }
    second_payload: dict[str, object] = {
        "ResponseSummary": {
            "RecordsFound": 2,
            "RowsReturned": 1,
            "Next": None,
        },
        "Results": [_loinc_result(code="67890-F")],
    }
    responses = [
        MockResponse(200, first_payload),
        MockResponse(200, second_payload),
    ]

    monkeypatch.setattr(loinc, "LOINC_USERNAME", "username")
    monkeypatch.setattr(loinc, "LOINC_PWD", "password")
    mocker.patch(
        "data_curation.terminologies.loinc.get_with_timeout",
        side_effect=responses,
    )

    result = loinc._process_loinc_valueset("https://example.com", "Lab Names")

    assert result[0]["code"] == "12345-F"
    assert result[1]["code"] == "67890-F"


def test_process_loinc_valueset_returns_none_when_next_page_errors(
    monkeypatch: pytest.MonkeyPatch, mocker
) -> None:
    first_payload: dict[str, object] = {
        "ResponseSummary": {
            "RecordsFound": 2,
            "RowsReturned": 1,
            "Next": "https://example.com/next",
        },
        "Results": [_loinc_result(code="12345-F")],
    }
    responses = [
        MockResponse(200, first_payload),
        MockResponse(500, {}, "TEST ERROR"),
    ]

    monkeypatch.setattr(loinc, "LOINC_USERNAME", "username")
    monkeypatch.setattr(loinc, "LOINC_PWD", "password")
    mocker.patch(
        "data_curation.terminologies.loinc.get_with_timeout",
        side_effect=responses,
    )

    with pytest.raises(
        RuntimeError, match=r"ERROR Retrieving LOINC Lab Names CODES: 500: TEST ERROR"
    ):
        loinc._process_loinc_valueset("https://example.com", "Lab Names")


def test_process_loinc_valueset_returns_none_on_error(
    monkeypatch: pytest.MonkeyPatch, mocker
) -> None:

    monkeypatch.setattr(loinc, "LOINC_USERNAME", "username")
    monkeypatch.setattr(loinc, "LOINC_PWD", "password")
    mocker.patch(
        "data_curation.terminologies.loinc.get_with_timeout",
        return_value=MockResponse(500, {}, "TEST ERROR"),
    )
    with pytest.raises(
        RuntimeError, match=r"ERROR Retrieving LOINC Lab Names CODES: 500: TEST ERROR"
    ):
        loinc._process_loinc_valueset("https://example.com", "Lab Names")


def test_process_loinc_valueset_requires_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(loinc, "LOINC_USERNAME", None)
    monkeypatch.setattr(loinc, "LOINC_PWD", None)

    with pytest.raises(KeyError):
        loinc._process_loinc_valueset("https://example.com", "Lab Names")


def test_process_loincs_for_umls_urls_processes_api_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload: dict[str, object] = {
        "ResponseSummary": {
            "RecordsFound": 1,
            "RowsReturned": 1,
            "Next": None,
        },
        "Results": [
            {
                "LOINC_NUM": "12345-F",
                "LONG_COMMON_NAME": "TEST LONG NAME",
            }
        ],
    }

    def mock_get_with_timeout(
        api_url: str,
        auth: tuple[str, str] | None = None,
    ) -> MockResponse:
        return MockResponse(200, payload)

    monkeypatch.setattr(loinc, "LOINC_USERNAME", "username")
    monkeypatch.setattr(loinc, "LOINC_PWD", "password")
    monkeypatch.setattr(loinc, "get_with_timeout", mock_get_with_timeout)

    result = loinc.process_loincs_for_umls_urls()

    assert result == {
        "12345-F": {
            "atom": loinc.UMLS_LOINC_LAB_ATOMS_URL + "12345-F/atoms",
            "crs": loinc.UMLS_LOINC_LAB_CROSSWALK_URL + "12345-F",
            "long_name": "TEST LONG NAME",
        }
    }


def test_process_loincs_for_umls_urls(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: dict[str, str] = {}
    expected = {
        "12345-F": {
            "atom": "TEST ATOM URL",
            "crs": "TEST CROSSWALK URL",
            "long_name": "TEST LONG NAME",
        }
    }

    def mock_process_loinc_valueset(
        api_url: str, loinc_vs_type: str
    ) -> list[dict[str, dict[str, str]]]:
        calls["api_url"] = api_url
        calls["loinc_vs_type"] = loinc_vs_type
        return [expected]

    monkeypatch.setattr(loinc, "_process_loinc_valueset", mock_process_loinc_valueset)

    result = loinc.process_loincs_for_umls_urls()

    assert result == expected
    assert calls["api_url"] == loinc.LOINC_BASE_URL + loinc.LOINC_LAB_NAMES_QUERY
    assert calls["loinc_vs_type"] == "UMLS Atoms"


def test_get_all_loinc_terms_per_code_filters_definition() -> None:
    loinc_result = _loinc_result()
    loinc_result["DefinitionDescription"] = loinc.LOINC_TEXT_TO_FILTER[0]

    result = loinc._get_all_loinc_terms_per_code(loinc_result, [])

    assert result[0]["definition_desc"] == ""


def test_get_loinc_consumer_names(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    consumer_names_file = tmp_path / "consumer_names.csv"
    consumer_names_file.write_text(
        "LoincNumber|ConsumerName\n12345-F|TEST CONSUMER NAME\n",
        encoding="utf-8",
    )
    rows: list[dict[str, str | None]] = [
        {"code": "12345-F"},
        {"code": "67890-F"},
    ]

    monkeypatch.setattr(loinc, "LOINC_CS_NAMES", consumer_names_file)

    result = loinc._get_loinc_consumer_names(rows)

    assert result == [
        {"code": "12345-F", "consumer_name": "TEST CONSUMER NAME"},
        {"code": "67890-F", "consumer_name": None},
    ]


def test_filter_loinc_term() -> None:
    assert loinc._filter_loinc_term(loinc.LOINC_TEXT_TO_FILTER[0])
    assert not loinc._filter_loinc_term("TEST DEFINITION")


def test_get_loinc_current_version_data(monkeypatch: pytest.MonkeyPatch, mocker) -> None:
    payload: dict[str, object] = {
        "releaseDate": "2026-01-02T00:00:00",
        "version": "2.80",
    }

    monkeypatch.setattr(loinc, "LOINC_USERNAME", "username")
    monkeypatch.setattr(loinc, "LOINC_PWD", "password")
    mocker.patch(
        "data_curation.terminologies.loinc.get_with_timeout",
        return_value=MockResponse(200, payload, json.dumps(payload)),
    )

    result = loinc.get_loinc_current_version_data()

    assert result == ("2.80", "2026-01-02")


def test_get_loinc_current_version_data_raises_on_error(
    monkeypatch: pytest.MonkeyPatch, mocker
) -> None:

    monkeypatch.setattr(loinc, "LOINC_USERNAME", "username")
    monkeypatch.setattr(loinc, "LOINC_PWD", "password")
    mocker.patch(
        "data_curation.terminologies.loinc.get_with_timeout",
        return_value=MockResponse(500, {}, "TEST ERROR"),
    )

    with pytest.raises(RuntimeError):
        loinc.get_loinc_current_version_data()


def test_get_loinc_current_version_data_requires_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(loinc, "LOINC_USERNAME", None)
    monkeypatch.setattr(loinc, "LOINC_PWD", None)

    with pytest.raises(KeyError):
        loinc.get_loinc_current_version_data()


def test_get_loinc_embedding_records(monkeypatch: pytest.MonkeyPatch) -> None:
    # current_loinc_dict = {
    #     "TYPE-CHANGE": _loinc_row(code="TYPE-CHANGE", lab_type="Order"),
    #     "TERM-CHANGE": _loinc_row(
    #         code="TERM-CHANGE",
    #         short_name="OLD SHORT NAME",
    #         long_name="OLD LONG NAME",
    #         display_name="OLD DISPLAY",
    #         full_name="OLD FULL NAME",
    #         consumer_name="OLD CONSUMER NAME",
    #     ),
    #     "NO-CHANGE": _loinc_row(code="NO-CHANGE"),
    # }
    delta_rows = [
        _loinc_row(code="NEW-CODE"),
        _loinc_row(code="TYPE-CHANGE", lab_type="Both"),
        _loinc_row(code="TERM-CHANGE"),
        _loinc_row(code="NO-CHANGE"),
    ]
    change_log: dict[str, object] = {}

    def mock_get_loinc_lab_names(
        version: str = "", include_consumer_names: bool = False
    ) -> list[dict[str, str]]:
        return delta_rows

    monkeypatch.setattr(loinc, "_get_loinc_lab_names", mock_get_loinc_lab_names)

    result = loinc.get_loinc_embedding_records(
        "2.80",
        "2026-02-23",
        "loinc_lab_names_20260223.csv",
    )
    emb_records = result["embedding_records"]
    descriptions = [record.get("description") for record in emb_records]
    emb_results = result.get("embedding_records")
    change_log = result.get("change_log")
    print(f"HERE: {emb_results}")

    assert "TEST SHORT NAME" in descriptions
    assert "TEST LONG NAME" in descriptions
    assert "TEST DISPLAY" in descriptions
    assert "TEST FULL NAME" in descriptions
    assert "TEST CONSUMER NAME" in descriptions
    expected_length = 20
    assert len(emb_results) == expected_length
    assert "Compared to file" in change_log
    assert "Changes" in change_log


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
        "class_type": "TEST CLASS",
    }
    result = loinc._create_embedding_record(140, loinc_term, loinc_term_type, loinc_axis)
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
    changes = ["short_name", "long_name"]

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
        "time_aspect": loinc_axis["time"],
        "system": loinc_axis["system"],
        "scale_type": loinc_axis["scale"],
        "method_type": loinc_axis["method"],
        "class_type": loinc_axis["class"],
    }
    record_2 = {
        "id": 157,
        "description": "ANOTHER TEST NAME",
        "description_vector": [],
        "loinc_type": loinc_axis["loinc_type"],
        "loinc_code": loinc_axis["loinc_code"],
        "loinc_name_type": "long_name",
        "property": loinc_axis["property"],
        "time_aspect": loinc_axis["time"],
        "system": loinc_axis["system"],
        "scale_type": loinc_axis["scale"],
        "method_type": loinc_axis["method"],
        "class_type": loinc_axis["class"],
    }
    expected = [record_1, record_2]
    result = loinc._create_embedding_records(loinc_id1, loinc_code, loinc_row, changes)
    assert result == expected


def test_create_embedding_records_w_updates() -> None:
    loinc_id1 = 155
    loinc_code = "12345-F"
    loinc_axis = {}
    loinc_axis["loinc_code"] = loinc_code
    loinc_axis["loinc_type"] = "Order"
    loinc_axis["property"] = "TEST PROPERTY"
    loinc_axis["time"] = "TEST TIME"
    loinc_axis["system"] = "TEST SYSTEM"
    loinc_axis["scale"] = "TEST SCALE"
    loinc_axis["method"] = "TEST METHOD"
    loinc_axis["class"] = "TEST CLASS"
    changes = ["loinc_type"]

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
        "id": "",
        "description": "TEST NAME",
        "description_vector": [],
        "loinc_type": loinc_axis["loinc_type"],
        "loinc_code": loinc_axis["loinc_code"],
        "loinc_name_type": "short_name",
        "property": loinc_axis["property"],
        "time_aspect": loinc_axis["time"],
        "system": loinc_axis["system"],
        "scale_type": loinc_axis["scale"],
        "method_type": loinc_axis["method"],
        "class_type": loinc_axis["class"],
    }
    record_2 = {
        "id": "",
        "description": "ANOTHER TEST NAME",
        "description_vector": [],
        "loinc_type": loinc_axis["loinc_type"],
        "loinc_code": loinc_axis["loinc_code"],
        "loinc_name_type": "long_name",
        "property": loinc_axis["property"],
        "time_aspect": loinc_axis["time"],
        "system": loinc_axis["system"],
        "scale_type": loinc_axis["scale"],
        "method_type": loinc_axis["method"],
        "class_type": loinc_axis["class"],
    }
    record_3 = {
        "id": "",
        "description": "TEST DISPLAY",
        "description_vector": [],
        "loinc_type": loinc_axis["loinc_type"],
        "loinc_code": loinc_axis["loinc_code"],
        "loinc_name_type": "display_name",
        "property": loinc_axis["property"],
        "time_aspect": loinc_axis["time"],
        "system": loinc_axis["system"],
        "scale_type": loinc_axis["scale"],
        "method_type": loinc_axis["method"],
        "class_type": loinc_axis["class"],
    }
    record_4 = {
        "id": "",
        "description": "TEST FULL NAME",
        "description_vector": [],
        "loinc_type": loinc_axis["loinc_type"],
        "loinc_code": loinc_axis["loinc_code"],
        "loinc_name_type": "full_name",
        "property": loinc_axis["property"],
        "time_aspect": loinc_axis["time"],
        "system": loinc_axis["system"],
        "scale_type": loinc_axis["scale"],
        "method_type": loinc_axis["method"],
        "class_type": loinc_axis["class"],
    }
    record_5 = {
        "id": "",
        "description": "TEST CONSUMER NAME",
        "description_vector": [],
        "loinc_type": loinc_axis["loinc_type"],
        "loinc_code": loinc_axis["loinc_code"],
        "loinc_name_type": "consumer_name",
        "property": loinc_axis["property"],
        "time_aspect": loinc_axis["time"],
        "system": loinc_axis["system"],
        "scale_type": loinc_axis["scale"],
        "method_type": loinc_axis["method"],
        "class_type": loinc_axis["class"],
    }
    expected = [record_1, record_2, record_3, record_4, record_5]
    result = loinc._create_embedding_records(loinc_id1, loinc_code, loinc_row, changes)
    assert result == expected


def test_create_embedding_records_with_no_consumer_name() -> None:
    loinc_id1 = 155
    loinc_code = "12345-F"
    loinc_row: dict[str, object] = dict(_loinc_row())
    loinc_row["consumer_name"] = None

    result = loinc._create_embedding_records(
        loinc_id1,
        loinc_code,
        loinc_row,
        ["consumer_name"],
    )

    assert result == []
