import pytest
from requests.models import Response

from data_curation.terminologies import http_client
from data_curation.terminologies.http_client import get_with_timeout


def test_get_with_timeout_calls_requests_get_with_timeout(
    monkeypatch: pytest.MonkeyPatch,
):
    response = Response()
    response.status_code = http_client.STATUS_CODE_OK
    calls: list[tuple[str, dict[str, object] | None, int | None, tuple[str, str] | None]] = []

    def fake_get(
        url: str,
        params: dict[str, object] | None = None,
        timeout: int | None = None,
        auth: tuple[str, str] | None = None,
    ) -> Response:
        calls.append((url, params, timeout, auth))

        return response

    monkeypatch.setattr(http_client.requests, "get", fake_get)

    result = get_with_timeout(
        "https://example.com",
        params={"code": "1234-5"},
        auth=("user", "password"),
    )

    assert result is response
    assert calls == [
        (
            "https://example.com",
            {"code": "1234-5"},
            60,
            ("user", "password"),
        )
    ]
