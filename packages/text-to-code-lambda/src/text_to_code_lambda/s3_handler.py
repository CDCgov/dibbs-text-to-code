import os
import typing

import boto3
from aws_lambda_typing import events as lambda_events
from botocore.client import BaseClient
from botocore.exceptions import ClientError
from opensearchpy import OpenSearch, RequestsHttpConnection
from requests_aws4auth import AWS4Auth


def require_env(name: str) -> str:
    """Fetch a required environment variable or raise a clear error.

    :param name: The name of the environment variable to fetch.
    :return: The value of the environment variable."""
    value = os.getenv(name)
    if not value:
        raise ValueError(f"{name} not set as an environment variable.")
    return value


def strip_protocol(url: str) -> str:
    """Remove http/https from a URL. This is sometimes needed for AWS service
    endpoints (like OpenSearch) that require the URL without the protocol.
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


def create_opensearch_client(aws_auth: AWS4Auth) -> OpenSearch:
    """
    Creates an OpenSearch client.

    :param aws_auth: AWS4Auth object for authentication
    :return: OpenSearch client
    """
    endpoint_url = require_env("OPENSEARCH_ENDPOINT_URL")
    return OpenSearch(
        hosts=[{"host": strip_protocol(endpoint_url), "port": 443}],
        http_auth=aws_auth,
        use_ssl=True,
        verify_certs=True,
        connection_class=RequestsHttpConnection,)


def get_file_content_from_s3(bucket_name: str, object_key: str) -> str:
    """
    Extracts the file content from an S3 bucket.

    :param bucket_name: The name of the S3 bucket.
    :param object_key: The key of the S3 object.
    :return: The content of the file as a string.
    """

    client = create_s3_client()

    # Check if object exists
    if not check_s3_object_exists(client, bucket_name, object_key):
        raise FileNotFoundError(f"S3 object not found: {bucket_name}/{object_key}")

    response = client.get_object(Bucket=bucket_name, Key=object_key)
    return response["Body"].read().decode("utf-8")

def get_eventbridge_data_from_s3_event(event: lambda_events.EventBridgeEvent) -> dict:
    """
    Extracts the file metadata from an S3 event triggered by a Lambda function.

    :param event: The S3 event containing the bucket and object key information.
    :return: A dictionary containing the bucket name and object key.
    """

    bucket_name = event["detail"]["bucket"]["name"]
    object_key = event["detail"]["object"]["key"]

    return {"bucket_name": bucket_name, "object_key": object_key}

def put_file(file_obj: typing.BinaryIO, bucket_name: str, object_key: str):
    """
    Uploads a file object to a S3 bucket.

    :param file_obj: The file object to upload.
    :param bucket_name: The name of the S3 bucket to upload to.
    :param object_key: The key to assign to the uploaded object in S3.
    """
    client = create_s3_client()
    client.put_object(Body=file_obj, Bucket=bucket_name, Key=object_key)


def check_s3_object_exists(s3_client: BaseClient, bucket: str, key: str) -> bool:
    """Checks that an S3 object exists.

    :param s3_client: The S3 client.
    :param bucket: The name of the S3 bucket.
    :param key: The key of the S3 object.
    :raises Exception: If an unexpected error occurs while fetching the S3 object.
    :return: True if the S3 object exists, False otherwise.
    """
    try:
        s3_client.head_object(Bucket=bucket, Key=key)
        return True
    except ClientError as e:
        error_code = e.response["Error"]["Code"]

        if error_code in ("404", "NoSuchKey"):
            return False

        raise Exception(f"Unexpected error while fetching file from S3: {key}", e)
    
def get_persistence_id(object_key: str, input_prefix: str) -> str:
    """Get the persistence_id from an S3 object key.

    Object key format: <pipeline-step>/<persistance_id>
    Example: TTCInput/2026/01/01/0026b704-f510-4494-8d21-11d27217d96e
    Returns: 2026/01/01/0026b704-f510-4494-8d21-11d27217d96e

    :param object_key: The S3 object key
    :param input_prefix: The pipeline step prefix (e.g., "TTCInput/")
    :return: The persistence_id portion of the key

    """
    if not object_key.startswith(input_prefix):
        raise ValueError(
            f"Object key '{object_key}' does not start with expected prefix '{input_prefix}'"
        )
    return object_key[len(input_prefix) :]