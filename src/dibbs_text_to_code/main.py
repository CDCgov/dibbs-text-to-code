import json
import logging
import typing

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

headers = (
    {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Credentials": True,
        "Content-Type": "application/json",
        "Access-Control-Allow-Methods": "DELETE,GET,HEAD,OPTIONS,PUT,POST,PATCH",
    },
)


# def handler(event: lambda_events.SQSEvent, context: lambda_context.Context):
def handler(event: typing.Dict[str, any], context=None):
    """
    Text to Code lambda entry point
    """

    print("✅ Lambda was invoked!", flush=True)
    try:
        print("📦 Event received:", json.dumps(event), flush=True)
        logger.info(f"Received event: {event}")
    except Exception as e:
        print(f"❌ Error serializing event: {e}", flush=True)
    logger.info("Lambda handler invoked")
    try:
        body = json.loads(event.get("body", "{}"))
    except json.JSONDecodeError:
        return {
            "statusCode": 400,
            "headers": headers,
            "body": json.dumps({"error": "Invalid JSON"}),
        }

    if body.get("mode") == "demo":
        return {
            "statusCode": 200,
            "headers": headers,
            "body": json.dumps(
                {
                    "message": "DIBBS Text to Code Demo!",
                    "event": body,
                }
            ),
        }

    return {
        "statusCode": 200,
        "headers": headers,
        "body": json.dumps(
            {
                "message": "DIBBS Text to Code!",
                # "event": body,
            }
        ),
    }
