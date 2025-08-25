import os
import typing

import boto3
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

    client = create_s3_client()

    response = client.get_object(Bucket=bucket_name, Key=object_key)
    return response["Body"].read()


def put_file(file_obj: typing.BinaryIO, bucket_name: str, object_key: str):
    """
    Uploads a file object to a S3 bucket.
    """
    client = create_s3_client()
    client.put_object(Body=file_obj, Bucket=bucket_name, Key=object_key)
