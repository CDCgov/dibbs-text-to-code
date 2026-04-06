"""Lambda handler: polls SQS (via event source mapping) for S3 event notificationsrouted through EventBridge, then reads the uploaded file from S3."""

import json

import boto3
from aws_lambda_powertools.utilities.typing import LambdaContext
from aws_lambda_typing.events import SQSEvent


def handler(event: SQSEvent, context: LambdaContext) -> dict:
    """Receives SQS messages containing EventBridge events for S3 PutObject.

    Each SQS record body is an EventBridge event like:
    {
        "source": "aws.s3",
        "detail-type": "Object Created",
        "detail": {
            "bucket": {"name": "my-bucket"},
            "object": {"key": "path/to/file.txt", "size": 123}
        }
    }
    """
    s3_client = boto3.client("s3")
    results = []

    for record in event["Records"]:
        body = json.loads(record["body"])
        detail = body["detail"]

        bucket = detail["bucket"]["name"]
        key = detail["object"]["key"]

        obj = s3_client.get_object(Bucket=bucket, Key=key)
        content = obj["Body"].read().decode("utf-8")

        results.append(
            {
                "bucket": bucket,
                "key": key,
                "content": content,
            },
        )

    return {"processed": len(results), "results": results}
