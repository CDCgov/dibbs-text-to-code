from aws_lambda_typing import context as lambda_context
from aws_lambda_typing import events as lambda_events


def handler(event: lambda_events.SQSEvent, context: lambda_context.Context) -> dict:
    """Augmentation lambda entry point."""
    return {"message": "DIBBS Augmentation!", "event": event}
