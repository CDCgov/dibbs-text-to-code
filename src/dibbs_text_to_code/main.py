import json
import os

import boto3
from aws_lambda_typing import context as lambda_context
from aws_lambda_typing import events as lambda_events
from botocore.client import BaseClient


def create_s3_client() -> BaseClient:
    """
    Creates an S3 client.
    """
    endpoint_url = os.getenv("S3_ENDPOINT_URL")
    region_name = os.getenv("AWS_REGION")

    return boto3.client("s3", endpoint_url=endpoint_url, region_name=region_name)


def get_file_content_from_s3_event(event: lambda_events.EventBridgeEvent) -> bytes:
    """
    Extracts the file content from an S3 event triggered by a Lambda function.
    """

    bucket_name = event["detail"]["bucket"]["name"]
    object_key = event["detail"]["object"]["key"]

    s3_client = create_s3_client()

    response = s3_client.get_object(Bucket=bucket_name, Key=object_key)
    return response["Body"].read()


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
