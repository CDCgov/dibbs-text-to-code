from typing import Any

import requests
from requests.models import Response

_TIMEOUT = 60

STATUS_CODE_OK = 200


def get_with_timeout(
    url: str,
    params: dict[str, Any] | None = None,
    auth: tuple[str, str] | None = None,
) -> Response:
    """JSON request with timeout of 60 seconds."""
    return requests.get(url, params=params, timeout=_TIMEOUT, auth=auth)
