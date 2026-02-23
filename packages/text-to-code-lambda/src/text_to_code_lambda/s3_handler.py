import os
import typing

import boto3
from aws_lambda_typing import events as lambda_events
from botocore.client import BaseClient
from opensearchpy import OpenSearch, RequestsHttpConnection
from requests_aws4auth import AWS4Auth


def require_env(name: str) -> str:
    """Fetch a required environment variable or raise a clear error.

    :param name: The name of the environment variable to fetch.
    :return: The value of the environment variable."""
    value = os.getenv(name)
    if not value:
        raise ValueError(f"{name} not set")
    return value


def strip_protocol(url: str) -> str:
    """Remove http/https from a URL.
    :param url: The URL to strip.
    :return: The URL without the protocol."""
    return url.removeprefix("https://").removeprefix("http://")


def get_s3_credentials():
    """Fetch AWS credentials from the environment """

    return boto3.Session().get_credentials()


def create_aws_auth() -> AWS4Auth:
    """
    Creates an AWS4Auth object for authenticating with AWS services.

    :return: AWS4Auth object
    """
    credentials = get_s3_credentials()
    
    return AWS4Auth(
        credentials.access_key,
        credentials.secret_key,
        require_env("AWS_REGION"),
        "es",
        session_token=credentials.token,
    )


def create_s3_client() -> BaseClient:
    """
    Creates an S3 client.

    :return: S3 client
    """
    endpoint_url = os.getenv("S3_ENDPOINT_URL")
    region_name = require_env("AWS_REGION")

    return boto3.client("s3", endpoint_url=endpoint_url, region_name=region_name)


def create_opensearch_client(awsauth: AWS4Auth) -> OpenSearch:
    """
    Creates an OpenSearch client.

    :param awsauth: AWS4Auth object for authentication
    :return: OpenSearch client
    """
    endpoint_url = require_env("OPENSEARCH_ENDPOINT_URL")
    return OpenSearch(
        hosts=[{"host": strip_protocol(endpoint_url), "port": 443}],
        http_auth=awsauth,
        use_ssl=True,
        verify_certs=True,
        connection_class=RequestsHttpConnection,)


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
