import json

from aws_lambda_typing import context as lambda_context
from aws_lambda_typing import events as lambda_events

from .s3_handler import get_file_content_from_s3_event


def handler(event: lambda_events.EventBridgeEvent, context: lambda_context.Context):
    """
    Text to Code lambda entry point
    """
    file_contents = []
    for record in event.get("Records", []):
        body = record.get("body")
        if not body:
            continue
        s3_event = json.loads(body)
        file_content = get_file_content_from_s3_event(s3_event)
        file_contents.append(file_content)

    return {"message": "DIBBS Text to Code!", "event": event, "file_contents": file_contents}
