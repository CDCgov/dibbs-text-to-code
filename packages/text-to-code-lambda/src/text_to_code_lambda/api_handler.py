"""AWS Lambda Function URL handler for the synchronous text-to-code demo API.

Deploys as a SECOND Lambda built from the same image as the SQS batch worker
(``lambda_function.py``), with the container ``CMD`` overridden to
``text_to_code_lambda.api_handler.handler``. It accepts a small JSON request and
returns LOINC suggestions, reusing the shared ``service`` module so the matching
logic is not duplicated.
"""

import json
import os
from base64 import b64decode

from aws_lambda_powertools import Logger
from aws_lambda_powertools.utilities.typing import LambdaContext

import lambda_handler

from . import service

logger = Logger(service="ttc-api")

# Backstop CORS origin. The Function URL's own CORS config is the real
# enforcement; this keeps responses usable if that config is ever absent.
CORS_ALLOW_ORIGIN = os.getenv("CORS_ALLOW_ORIGIN", "*")

_CORS_HEADERS = {
    "content-type": "application/json",
    "access-control-allow-origin": CORS_ALLOW_ORIGIN,
    "access-control-allow-headers": "content-type",
    "access-control-allow-methods": "POST, OPTIONS",
}

# Guardrail so a single request can't fan out into an unbounded number of model runs.
MAX_INPUTS = 100


def _response(status_code: int, body: dict) -> dict:
    return {
        "statusCode": status_code,
        "headers": _CORS_HEADERS,
        "body": json.dumps(body),
    }


def _get_body(event: dict) -> dict:
    raw = event.get("body")
    if not raw:
        return {}
    if event.get("isBase64Encoded"):
        raw = b64decode(raw).decode("utf-8")
    return json.loads(raw)


def _request_method(event: dict) -> str | None:
    return event.get("requestContext", {}).get("http", {}).get("method")


@logger.inject_lambda_context
def handler(event: dict, context: LambdaContext) -> dict:
    """Handle a Function URL request mapping lab text strings to LOINC codes.

    Request body: ``{"inputs": ["Glucose measurement", ...], "data_field": "Lab Test Name Ordered"}``
    (``data_field`` optional; a single ``{"text": "..."}`` is also accepted).
    Response: ``{"results": [...]}`` (see ``service._to_result`` for the row shape).

    :param event: The Lambda Function URL / API Gateway v2 proxy event.
    :param context: The Lambda context object.
    :return: A proxy response dict with a JSON body and CORS headers.
    """
    if _request_method(event) == "OPTIONS":
        return {"statusCode": 204, "headers": _CORS_HEADERS, "body": ""}

    try:
        body = _get_body(event)
    except ValueError, TypeError:
        return _response(400, {"error": "Request body must be valid JSON."})

    inputs = body.get("inputs")
    if inputs is None and isinstance(body.get("text"), str):
        inputs = [body["text"]]

    if not isinstance(inputs, list) or not all(isinstance(item, str) for item in inputs):
        return _response(400, {"error": "Request must include `inputs` as a list of strings."})

    if len(inputs) > MAX_INPUTS:
        return _response(400, {"error": f"Too many inputs; limit is {MAX_INPUTS} per request."})

    data_field = service.parse_data_field(body.get("data_field"))
    opensearch_client = lambda_handler.create_opensearch_client()

    logger.info(
        "Processing text-to-code request",
        num_inputs=len(inputs),
        data_field=data_field,
        status="processing",
    )
    results = service.results_for_inputs(inputs, data_field, opensearch_client)

    return _response(200, {"results": results})
