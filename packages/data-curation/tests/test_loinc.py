import json
from pathlib import Path

import pytest

from data_curation.terminologies import loinc
from data_curation.terminologies.general import load_local_extract_file_to_dict

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


def _loinc_payload(
    results: list[dict[str, str]],
    next_url: str | None = None,
    rows_returned: int | None = None,
) -> dict[str, object]:
    returned_rows = len(results) if rows_returned is None else rows_returned
    return {
        "ResponseSummary": {
            "RecordsFound": len(results),
            "RowsReturned": returned_rows,
            "Next": next_url,
        },
        "Results": results,
    }


def test_set_loinc_response_uses_default_collections() -> None:
    result = loinc.set_loinc_response(
        terminology_set=loinc.LAB_NAMES,
        result="success",
        message="TEST MESSAGE",
    )

    assert result == {
        "terminology": loinc.LAB_NAMES,
        "result": "success",
        "message": "TEST MESSAGE",
        "change_log": {},
        "embedding_records": [],
    }


def test_set_loinc_response_uses_provided_collections() -> None:
    change_log = {"Changes": {"new_loinc": 1}}
    embedding_records = [{"id": 1}]

    result = loinc.set_loinc_response(
        terminology_set=loinc.LAB_NAMES,
        result="success",
        message="TEST MESSAGE",
        change_log=change_log,
        embedding_records=embedding_records,
    )

    assert result == {
        "terminology": loinc.LAB_NAMES,
        "result": "success",
        "message": "TEST MESSAGE",
        "change_log": change_log,
        "embedding_records": embedding_records,
    }


def test_extract_full_loinc_lab_names(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = _loinc_payload([_loinc_result()])
    consumer_names_file = tmp_path / "consumer_names.csv"
    consumer_names_file.write_text(
        "LoincNumber|ConsumerName\n12345-F|TEST CONSUMER NAME\n",
        encoding="utf-8",
    )

    def mock_get_with_timeout(
        api_url: str,
        auth: tuple[str, str] | None = None,
    ) -> MockResponse:
        return MockResponse(200, payload)

    monkeypatch.setattr(loinc, "LOINC_USERNAME", "username")
    monkeypatch.setattr(loinc, "LOINC_PWD", "password")
    monkeypatch.setattr(loinc, "LOINC_CS_NAMES", consumer_names_file)
    monkeypatch.setattr(loinc, "get_with_timeout", mock_get_with_timeout)

    result = loinc.extract_full_loinc_lab_names(include_consumer_names=True)

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
            "consumer_name": "TEST CONSUMER NAME",
        }
    ]


def test_extract_full_loinc_lab_names_handles_empty_api_results(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    payload = _loinc_payload([], rows_returned=1)
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


def test_extract_full_loinc_lab_orders(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []
    payload = _loinc_payload([_loinc_result(lab_type="Order")])
    consumer_names_file = tmp_path / "consumer_names.csv"
    consumer_names_file.write_text(
        "LoincNumber|ConsumerName\n12345-F|TEST CONSUMER NAME\n",
        encoding="utf-8",
    )

    def mock_get_with_timeout(
        api_url: str,
        auth: tuple[str, str] | None = None,
    ) -> MockResponse:
        calls.append(api_url)
        return MockResponse(200, payload)

    monkeypatch.setattr(loinc, "LOINC_USERNAME", "username")
    monkeypatch.setattr(loinc, "LOINC_PWD", "password")
    monkeypatch.setattr(loinc, "LOINC_CS_NAMES", consumer_names_file)
    monkeypatch.setattr(loinc, "get_with_timeout", mock_get_with_timeout)

    results = loinc.extract_full_loinc_lab_orders(include_consumer_names=True)

    assert len(results) == 1
    assert results[0].get("code") == "12345-F"
    assert results[0].get("consumer_name") == "TEST CONSUMER NAME"
    assert results[0].get("lab_type") == "Order"
    assert calls == [loinc.LOINC_BASE_URL + f"query={loinc.LOINC_LAB_ORDER_QUERY}"]


def test_extract_full_loinc_lab_orders_with_version(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []
    payload = _loinc_payload([_loinc_result(lab_type="Order")])

    def mock_get_with_timeout(
        api_url: str,
        auth: tuple[str, str] | None = None,
    ) -> MockResponse:
        calls.append(api_url)
        return MockResponse(200, payload)

    monkeypatch.setattr(loinc, "LOINC_USERNAME", "username")
    monkeypatch.setattr(loinc, "LOINC_PWD", "password")
    monkeypatch.setattr(loinc, "get_with_timeout", mock_get_with_timeout)

    result = loinc.extract_full_loinc_lab_orders(version="2.80")

    assert len(result) == 1
    assert result[0]["lab_type"] == "Order"
    assert calls == [
        loinc.LOINC_BASE_URL + f"query=versionlastchanged:2.80+AND+{loinc.LOINC_LAB_ORDER_QUERY}"
    ]


def test_extract_full_loinc_lab_results(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []
    payload = _loinc_payload([_loinc_result(lab_type="Observation")])
    consumer_names_file = tmp_path / "consumer_names.csv"
    consumer_names_file.write_text(
        "LoincNumber|ConsumerName\n12345-F|TEST CONSUMER NAME\n",
        encoding="utf-8",
    )

    def mock_get_with_timeout(
        api_url: str,
        auth: tuple[str, str] | None = None,
    ) -> MockResponse:
        calls.append(api_url)
        return MockResponse(200, payload)

    monkeypatch.setattr(loinc, "LOINC_USERNAME", "username")
    monkeypatch.setattr(loinc, "LOINC_PWD", "password")
    monkeypatch.setattr(loinc, "LOINC_CS_NAMES", consumer_names_file)
    monkeypatch.setattr(loinc, "get_with_timeout", mock_get_with_timeout)

    results = loinc.extract_full_loinc_lab_results(include_consumer_names=True)

    assert len(results) == 1
    assert results[0].get("code") == "12345-F"
    assert results[0].get("consumer_name") == "TEST CONSUMER NAME"
    assert results[0].get("lab_type") == "Observation"
    assert calls == [loinc.LOINC_BASE_URL + f"query={loinc.LOINC_LAB_RESULT_QUERY}"]


def test_extract_full_loinc_lab_results_with_version(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []
    payload = _loinc_payload([_loinc_result(lab_type="Observation")])

    def mock_get_with_timeout(
        api_url: str,
        auth: tuple[str, str] | None = None,
    ) -> MockResponse:
        calls.append(api_url)
        return MockResponse(200, payload)

    monkeypatch.setattr(loinc, "LOINC_USERNAME", "username")
    monkeypatch.setattr(loinc, "LOINC_PWD", "password")
    monkeypatch.setattr(loinc, "get_with_timeout", mock_get_with_timeout)

    result = loinc.extract_full_loinc_lab_results(version="2.80")

    assert len(result) == 1
    assert result[0]["lab_type"] == "Observation"
    assert calls == [
        loinc.LOINC_BASE_URL + f"query=versionlastchanged:2.80+AND+{loinc.LOINC_LAB_RESULT_QUERY}"
    ]


def test_extract_full_loinc_lab_names_uses_expected_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []
    payload = _loinc_payload([_loinc_result()])

    def mock_get_with_timeout(
        api_url: str,
        auth: tuple[str, str] | None = None,
    ) -> MockResponse:
        calls.append(api_url)
        return MockResponse(200, payload)

    monkeypatch.setattr(loinc, "LOINC_USERNAME", "username")
    monkeypatch.setattr(loinc, "LOINC_PWD", "password")
    monkeypatch.setattr(loinc, "get_with_timeout", mock_get_with_timeout)

    result = loinc.extract_full_loinc_lab_names()

    assert len(result) == 1
    assert calls == [loinc.LOINC_BASE_URL + f"query={loinc.LOINC_LAB_NAMES_QUERY}"]


def test_extract_full_loinc_lab_names_gets_next_page(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first_payload = _loinc_payload(
        [_loinc_result(code="12345-F")],
        next_url="https://example.com/next",
    )
    second_payload = _loinc_payload([_loinc_result(code="67890-F")])
    responses = [
        MockResponse(200, first_payload),
        MockResponse(200, second_payload),
    ]

    def mock_get_with_timeout(
        api_url: str,
        auth: tuple[str, str] | None = None,
    ) -> MockResponse:
        return responses.pop(0)

    monkeypatch.setattr(loinc, "LOINC_USERNAME", "username")
    monkeypatch.setattr(loinc, "LOINC_PWD", "password")
    monkeypatch.setattr(loinc, "get_with_timeout", mock_get_with_timeout)

    result = loinc.extract_full_loinc_lab_names()

    assert result[0]["code"] == "12345-F"
    assert result[1]["code"] == "67890-F"


def test_extract_full_loinc_lab_names_raises_when_next_page_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first_payload = _loinc_payload(
        [_loinc_result(code="12345-F")],
        next_url="https://example.com/next",
    )
    responses = [
        MockResponse(200, first_payload),
        MockResponse(500, {}, "TEST ERROR"),
    ]

    def mock_get_with_timeout(
        api_url: str,
        auth: tuple[str, str] | None = None,
    ) -> MockResponse:
        return responses.pop(0)

    monkeypatch.setattr(loinc, "LOINC_USERNAME", "username")
    monkeypatch.setattr(loinc, "LOINC_PWD", "password")
    monkeypatch.setattr(loinc, "get_with_timeout", mock_get_with_timeout)

    with pytest.raises(
        RuntimeError, match=r"ERROR Retrieving LOINC Lab Names CODES: 500: TEST ERROR"
    ):
        loinc.extract_full_loinc_lab_names()


def test_extract_full_loinc_lab_names_raises_on_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def mock_get_with_timeout(
        api_url: str,
        auth: tuple[str, str] | None = None,
    ) -> MockResponse:
        return MockResponse(500, {}, "TEST ERROR")

    monkeypatch.setattr(loinc, "LOINC_USERNAME", "username")
    monkeypatch.setattr(loinc, "LOINC_PWD", "password")
    monkeypatch.setattr(loinc, "get_with_timeout", mock_get_with_timeout)

    with pytest.raises(
        RuntimeError, match=r"ERROR Retrieving LOINC Lab Names CODES: 500: TEST ERROR"
    ):
        loinc.extract_full_loinc_lab_names()


def test_extract_full_loinc_lab_names_requires_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(loinc, "LOINC_USERNAME", None)
    monkeypatch.setattr(loinc, "LOINC_PWD", None)

    with pytest.raises(KeyError):
        loinc.extract_full_loinc_lab_names()


def test_process_loincs_for_umls_urls_processes_api_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = _loinc_payload(
        [
            {
                "LOINC_NUM": "12345-F",
                "LONG_COMMON_NAME": "TEST LONG NAME",
            }
        ]
    )

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


def test_process_loincs_for_umls_urls_gets_next_page(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first_payload = _loinc_payload(
        [
            {
                "LOINC_NUM": "12345-F",
                "LONG_COMMON_NAME": "TEST LONG NAME",
            }
        ],
        next_url="https://example.com/next",
    )
    second_payload = _loinc_payload(
        [
            {
                "LOINC_NUM": "67890-F",
                "LONG_COMMON_NAME": "ANOTHER TEST LONG NAME",
            }
        ]
    )
    responses = [
        MockResponse(200, first_payload),
        MockResponse(200, second_payload),
    ]

    def mock_get_with_timeout(
        api_url: str,
        auth: tuple[str, str] | None = None,
    ) -> MockResponse:
        return responses.pop(0)

    monkeypatch.setattr(loinc, "LOINC_USERNAME", "username")
    monkeypatch.setattr(loinc, "LOINC_PWD", "password")
    monkeypatch.setattr(loinc, "get_with_timeout", mock_get_with_timeout)

    result = loinc.process_loincs_for_umls_urls()

    assert result == {
        "12345-F": {
            "atom": loinc.UMLS_LOINC_LAB_ATOMS_URL + "12345-F/atoms",
            "crs": loinc.UMLS_LOINC_LAB_CROSSWALK_URL + "12345-F",
            "long_name": "TEST LONG NAME",
        },
        "67890-F": {
            "atom": loinc.UMLS_LOINC_LAB_ATOMS_URL + "67890-F/atoms",
            "crs": loinc.UMLS_LOINC_LAB_CROSSWALK_URL + "67890-F",
            "long_name": "ANOTHER TEST LONG NAME",
        },
    }


def test_extract_full_loinc_lab_names_filters_definition(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    loinc_result = _loinc_result()
    loinc_result["DefinitionDescription"] = loinc.LOINC_TEXT_TO_FILTER[0]
    payload = _loinc_payload([loinc_result])

    def mock_get_with_timeout(
        api_url: str,
        auth: tuple[str, str] | None = None,
    ) -> MockResponse:
        return MockResponse(200, payload)

    monkeypatch.setattr(loinc, "LOINC_USERNAME", "username")
    monkeypatch.setattr(loinc, "LOINC_PWD", "password")
    monkeypatch.setattr(loinc, "get_with_timeout", mock_get_with_timeout)

    result = loinc.extract_full_loinc_lab_names()

    assert result[0]["definition_desc"] == ""


def test_extract_full_loinc_lab_names_preserves_unfiltered_definition(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = _loinc_payload([_loinc_result()])

    def mock_get_with_timeout(
        api_url: str,
        auth: tuple[str, str] | None = None,
    ) -> MockResponse:
        return MockResponse(200, payload)

    monkeypatch.setattr(loinc, "LOINC_USERNAME", "username")
    monkeypatch.setattr(loinc, "LOINC_PWD", "password")
    monkeypatch.setattr(loinc, "get_with_timeout", mock_get_with_timeout)

    result = loinc.extract_full_loinc_lab_names()

    assert result[0]["definition_desc"] == "TEST DEFINITION"


def test_extract_full_loinc_lab_names_adds_available_consumer_names(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = _loinc_payload(
        [
            _loinc_result(code="12345-F"),
            _loinc_result(code="67890-F"),
        ]
    )
    consumer_names_file = tmp_path / "consumer_names.csv"
    consumer_names_file.write_text(
        "LoincNumber|ConsumerName\n12345-F|TEST CONSUMER NAME\n",
        encoding="utf-8",
    )

    def mock_get_with_timeout(
        api_url: str,
        auth: tuple[str, str] | None = None,
    ) -> MockResponse:
        return MockResponse(200, payload)

    monkeypatch.setattr(loinc, "LOINC_USERNAME", "username")
    monkeypatch.setattr(loinc, "LOINC_PWD", "password")
    monkeypatch.setattr(loinc, "LOINC_CS_NAMES", consumer_names_file)
    monkeypatch.setattr(loinc, "get_with_timeout", mock_get_with_timeout)

    result = loinc.extract_full_loinc_lab_names(include_consumer_names=True)

    assert result[0]["consumer_name"] == "TEST CONSUMER NAME"
    assert result[1]["consumer_name"] is None


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
    delta_rows = [
        _loinc_result(code="NEW-CODE"),
        _loinc_result(code="TYPE-CHANGE", lab_type="Both"),
        _loinc_result(code="TERM-CHANGE"),
        _loinc_result(code="NO-CHANGE"),
    ]
    payload = _loinc_payload(delta_rows)
    requested_urls: list[str] = []
    change_log: dict[str, object] = {}

    def mock_get_with_timeout(
        api_url: str,
        auth: tuple[str, str] | None = None,
    ) -> MockResponse:
        requested_urls.append(api_url)
        return MockResponse(200, payload)

    monkeypatch.setattr(loinc, "LOINC_USERNAME", "username")
    monkeypatch.setattr(loinc, "LOINC_PWD", "password")
    monkeypatch.setattr(loinc, "get_with_timeout", mock_get_with_timeout)

    loinc_file_contents = load_local_extract_file_to_dict("loinc_lab_names_20260223.csv")

    result = loinc.get_loinc_embedding_records(
        "2.80",
        "2026-02-23",
        loinc_file_contents,
    )
    emb_records = result["embedding_records"]
    descriptions = [record.get("description") for record in emb_records]
    emb_results = result.get("embedding_records")
    change_log = result.get("change_log")

    assert "TEST SHORT NAME" in descriptions
    assert "TEST LONG NAME" in descriptions
    assert "TEST DISPLAY" in descriptions
    assert "TEST FULL NAME" in descriptions
    expected_length = 16
    assert len(emb_results) == expected_length
    assert "Compared to file" in change_log
    assert "Changes" in change_log
    assert requested_urls == [
        loinc.LOINC_BASE_URL + f"query=versionlastchanged:2.80+AND+{loinc.LOINC_LAB_NAMES_QUERY}"
    ]


def test_get_loinc_embedding_records_handles_existing_records(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    expected_embedding_records_count = 12
    delta_rows = [
        _loinc_result(code="NEW-CODE"),
        _loinc_result(code="TYPE-CHANGE", lab_type="Both"),
        _loinc_result(code="TERM-CHANGE"),
        _loinc_result(code="NO-CHANGE"),
    ]
    payload = _loinc_payload(delta_rows)
    current_loinc_file = {
        "TYPE-CHANGE": _loinc_row(
            code="TYPE-CHANGE",
            lab_type="Order",
        ),
        "TERM-CHANGE": _loinc_row(
            code="TERM-CHANGE",
            short_name="OLD SHORT NAME",
            long_name="OLD LONG NAME",
            display_name="OLD DISPLAY",
            full_name="OLD FULL NAME",
        ),
        "NO-CHANGE": _loinc_row(code="NO-CHANGE"),
    }

    def mock_get_with_timeout(
        api_url: str,
        auth: tuple[str, str] | None = None,
    ) -> MockResponse:
        return MockResponse(200, payload)

    monkeypatch.setattr(loinc, "LOINC_USERNAME", "username")
    monkeypatch.setattr(loinc, "LOINC_PWD", "password")
    monkeypatch.setattr(loinc, "get_with_timeout", mock_get_with_timeout)

    result = loinc.get_loinc_embedding_records(
        "2.80",
        "2026-02-23",
        current_loinc_file,
    )

    assert (
        result["message"] == f"Updated {expected_embedding_records_count} LOINC Embedding Records!"
    )
    assert len(result["embedding_records"]) == expected_embedding_records_count
    assert result["change_log"] == {
        "New Loinc Version": "2.80 as of 2026-02-23",
        "Compared to file": current_loinc_file,
        "Changes": {
            "new_loinc": 1,
            "short_name": 1,
            "long_name": 1,
            "display_name": 1,
            "full_name": 1,
            "loinc_type": 1,
        },
    }


def test_get_loinc_embedding_records_creates_expected_records(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = _loinc_payload(
        [
            _loinc_result(
                code="12345-F",
                short_name="TEST NAME",
                long_name="ANOTHER TEST NAME",
                display_name="TEST DISPLAY",
                full_name="TEST FULL NAME",
                lab_type="Both",
            )
        ]
    )

    def mock_get_with_timeout(
        api_url: str,
        auth: tuple[str, str] | None = None,
    ) -> MockResponse:
        return MockResponse(200, payload)

    monkeypatch.setattr(loinc, "LOINC_USERNAME", "username")
    monkeypatch.setattr(loinc, "LOINC_PWD", "password")
    monkeypatch.setattr(loinc, "get_with_timeout", mock_get_with_timeout)

    result = loinc.get_loinc_embedding_records(
        "2.80",
        "2026-02-23",
        {},
    )

    assert result["embedding_records"] == [
        {
            "id": 1,
            "description": "TEST NAME",
            "description_vector": [],
            "loinc_type": "Both",
            "loinc_code": "12345-F",
            "loinc_name_type": "short_name",
            "property": "TEST PROPERTY",
            "time_aspect": "TEST TIME",
            "system": "TEST SYSTEM",
            "scale_type": "TEST SCALE",
            "method_type": "TEST METHOD",
            "class_type": "TEST CLASS",
        },
        {
            "id": 2,
            "description": "ANOTHER TEST NAME",
            "description_vector": [],
            "loinc_type": "Both",
            "loinc_code": "12345-F",
            "loinc_name_type": "long_name",
            "property": "TEST PROPERTY",
            "time_aspect": "TEST TIME",
            "system": "TEST SYSTEM",
            "scale_type": "TEST SCALE",
            "method_type": "TEST METHOD",
            "class_type": "TEST CLASS",
        },
        {
            "id": 3,
            "description": "TEST DISPLAY",
            "description_vector": [],
            "loinc_type": "Both",
            "loinc_code": "12345-F",
            "loinc_name_type": "display_name",
            "property": "TEST PROPERTY",
            "time_aspect": "TEST TIME",
            "system": "TEST SYSTEM",
            "scale_type": "TEST SCALE",
            "method_type": "TEST METHOD",
            "class_type": "TEST CLASS",
        },
        {
            "id": 4,
            "description": "TEST FULL NAME",
            "description_vector": [],
            "loinc_type": "Both",
            "loinc_code": "12345-F",
            "loinc_name_type": "full_name",
            "property": "TEST PROPERTY",
            "time_aspect": "TEST TIME",
            "system": "TEST SYSTEM",
            "scale_type": "TEST SCALE",
            "method_type": "TEST METHOD",
            "class_type": "TEST CLASS",
        },
    ]


def test_get_loinc_embedding_records_creates_type_update_records(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = _loinc_payload(
        [
            _loinc_result(
                code="12345-F",
                short_name="TEST NAME",
                long_name="ANOTHER TEST NAME",
                display_name="TEST DISPLAY",
                full_name="TEST FULL NAME",
                lab_type="Order",
            )
        ]
    )
    current_loinc_file = {
        "12345-F": _loinc_row(
            code="12345-F",
            short_name="TEST NAME",
            long_name="ANOTHER TEST NAME",
            display_name="TEST DISPLAY",
            full_name="TEST FULL NAME",
            lab_type="Observation",
        )
    }

    def mock_get_with_timeout(
        api_url: str,
        auth: tuple[str, str] | None = None,
    ) -> MockResponse:
        return MockResponse(200, payload)

    monkeypatch.setattr(loinc, "LOINC_USERNAME", "username")
    monkeypatch.setattr(loinc, "LOINC_PWD", "password")
    monkeypatch.setattr(loinc, "get_with_timeout", mock_get_with_timeout)

    result = loinc.get_loinc_embedding_records(
        "2.80",
        "2026-02-23",
        current_loinc_file,
    )

    assert result["embedding_records"] == [
        {
            "id": "",
            "description": "TEST NAME",
            "description_vector": [],
            "loinc_type": "Order",
            "loinc_code": "12345-F",
            "loinc_name_type": "short_name",
            "property": "TEST PROPERTY",
            "time_aspect": "TEST TIME",
            "system": "TEST SYSTEM",
            "scale_type": "TEST SCALE",
            "method_type": "TEST METHOD",
            "class_type": "TEST CLASS",
        },
        {
            "id": "",
            "description": "ANOTHER TEST NAME",
            "description_vector": [],
            "loinc_type": "Order",
            "loinc_code": "12345-F",
            "loinc_name_type": "long_name",
            "property": "TEST PROPERTY",
            "time_aspect": "TEST TIME",
            "system": "TEST SYSTEM",
            "scale_type": "TEST SCALE",
            "method_type": "TEST METHOD",
            "class_type": "TEST CLASS",
        },
        {
            "id": "",
            "description": "TEST DISPLAY",
            "description_vector": [],
            "loinc_type": "Order",
            "loinc_code": "12345-F",
            "loinc_name_type": "display_name",
            "property": "TEST PROPERTY",
            "time_aspect": "TEST TIME",
            "system": "TEST SYSTEM",
            "scale_type": "TEST SCALE",
            "method_type": "TEST METHOD",
            "class_type": "TEST CLASS",
        },
        {
            "id": "",
            "description": "TEST FULL NAME",
            "description_vector": [],
            "loinc_type": "Order",
            "loinc_code": "12345-F",
            "loinc_name_type": "full_name",
            "property": "TEST PROPERTY",
            "time_aspect": "TEST TIME",
            "system": "TEST SYSTEM",
            "scale_type": "TEST SCALE",
            "method_type": "TEST METHOD",
            "class_type": "TEST CLASS",
        },
    ]


def test_get_loinc_embedding_records_ignores_consumer_name_only_changes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = _loinc_payload([_loinc_result(code="12345-F")])
    current_loinc_file = {
        "12345-F": _loinc_row(
            code="12345-F",
            consumer_name="OLD CONSUMER NAME",
        )
    }

    def mock_get_with_timeout(
        api_url: str,
        auth: tuple[str, str] | None = None,
    ) -> MockResponse:
        return MockResponse(200, payload)

    monkeypatch.setattr(loinc, "LOINC_USERNAME", "username")
    monkeypatch.setattr(loinc, "LOINC_PWD", "password")
    monkeypatch.setattr(loinc, "get_with_timeout", mock_get_with_timeout)

    result = loinc.get_loinc_embedding_records(
        "2.80",
        "2026-02-23",
        current_loinc_file,
    )

    assert result["embedding_records"] == []
    assert result["change_log"]["Changes"] == {
        "new_loinc": 0,
        "short_name": 0,
        "long_name": 0,
        "display_name": 0,
        "full_name": 0,
        "loinc_type": 0,
    }
