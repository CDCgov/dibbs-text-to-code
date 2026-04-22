import os
import typing

import boto3
from aws_lambda_typing import events as lambda_events
from botocore.client import BaseClient
from botocore.credentials import Credentials
from botocore.exceptions import ClientError
from opensearchpy import OpenSearch
from opensearchpy import RequestsHttpConnection
from requests_aws4auth import AWS4Auth

from .models import OpenSearchResult

_cached_aws_auth: AWS4Auth | None = None
_cached_aws_auth_key: tuple[str | None, str | None, str | None] | None = None
_cached_s3_client: BaseClient | None = None
_cached_s3_client_key: tuple[str | None, str | None, str | None, str | None] | None = None
_cached_opensearch_client: OpenSearch | None = None


def require_env(name: str) -> str:
    """Fetch a required environment variable or raise a clear error.

    :param name: The name of the environment variable to fetch.
    :return: The value of the environment variable.
    """
    value = os.getenv(name)
    if not value:
        raise ValueError(f"{name} not set as an environment variable.")
    return value


def strip_protocol(url: str) -> str:
    """Remove http/https from a URL.

    This is sometimes needed for AWS service
    endpoints (like OpenSearch) that require the URL without the protocol.
    :param url: The URL to strip.
    :return: The URL without the protocol.
    """
    return url.removeprefix("https://").removeprefix("http://")


def get_s3_credentials() -> Credentials:
    """Fetch AWS credentials from the environment."""
    return boto3.Session().get_credentials()


def create_aws_auth() -> AWS4Auth:
    """Creates an AWS4Auth object for authenticating with AWS services.

    :return: AWS4Auth object
    """
    global _cached_aws_auth  # noqa: PLW0603
    global _cached_aws_auth_key  # noqa: PLW0603

    credentials = get_s3_credentials()
    cache_key = (
        credentials.access_key,
        credentials.secret_key,
        credentials.token,
    )

    if _cached_aws_auth is None or _cached_aws_auth_key != cache_key:
        _cached_aws_auth = AWS4Auth(
            credentials.access_key,
            credentials.secret_key,
            require_env("AWS_REGION"),
            "es",
            session_token=credentials.token,
        )
        _cached_aws_auth_key = cache_key

    return _cached_aws_auth


def create_s3_client() -> BaseClient:
    """Creates an S3 client.

    :return: S3 client
    """
    global _cached_s3_client  # noqa: PLW0603
    global _cached_s3_client_key  # noqa: PLW0603

    endpoint_url = os.getenv("S3_ENDPOINT_URL")
    region_name = require_env("AWS_REGION")
    credentials = get_s3_credentials()
    cache_key = (
        endpoint_url,
        region_name,
        credentials.access_key,
        credentials.secret_key,
    )

    if _cached_s3_client is None or _cached_s3_client_key != cache_key:
        _cached_s3_client = boto3.client(
            "s3",
            endpoint_url=endpoint_url,
            region_name=region_name,
            aws_access_key_id=credentials.access_key,
            aws_secret_access_key=credentials.secret_key,
            aws_session_token=credentials.token,
        )
        _cached_s3_client_key = cache_key

    return _cached_s3_client


def create_opensearch_client(aws_auth: AWS4Auth | None = None) -> OpenSearch:
    """Creates an OpenSearch client.

    :param aws_auth: AWS4Auth object for authentication
    :return: OpenSearch client
    """
    global _cached_opensearch_client  # noqa: PLW0603

    if _cached_opensearch_client is None:
        endpoint_url = require_env("OPENSEARCH_ENDPOINT_URL")
        auth = aws_auth or create_aws_auth()
        _cached_opensearch_client = OpenSearch(
            hosts=[{"host": strip_protocol(endpoint_url), "port": 443}],
            http_auth=auth,
            use_ssl=True,
            verify_certs=True,
            connection_class=RequestsHttpConnection,
        )

    return _cached_opensearch_client


def get_file_content_from_s3(
    bucket_name: str, object_key: str, s3_client: BaseClient | None = None
) -> str:
    """Extracts the file content from an S3 bucket.

    :param bucket_name: The name of the S3 bucket.
    :param object_key: The key of the S3 object.
    :param s3_client: Optional pre-created S3 client. If None, a new client is created.
    :return: The content of the file as a string.
    """
    client = s3_client or create_s3_client()

    # Check if object exists
    if not check_s3_object_exists(client, bucket_name, object_key):
        raise FileNotFoundError(f"S3 object not found: {bucket_name}/{object_key}")

    response = client.get_object(Bucket=bucket_name, Key=object_key)
    return response["Body"].read().decode("utf-8")


def get_eventbridge_data_from_s3_event(event: lambda_events.EventBridgeEvent) -> dict:
    """Extracts the file metadata from an S3 event triggered by a Lambda function.

    :param event: The S3 event containing the bucket and object key information.
    :return: A dictionary containing the bucket name and object key.
    """
    bucket_name = event.get("detail", {}).get("bucket", {}).get("name")
    object_key = event["detail"]["object"]["key"]

    return {"bucket_name": bucket_name, "object_key": object_key}


def put_file(
    file_obj: typing.BinaryIO,
    bucket_name: str,
    object_key: str,
    s3_client: BaseClient | None = None,
) -> None:
    """Uploads a file object to a S3 bucket.

    :param file_obj: The file object to upload.
    :param bucket_name: The name of the S3 bucket to upload to.
    :param object_key: The key to assign to the uploaded object in S3.
    :param s3_client: Optional pre-created S3 client. If None, a new client is created.
    """
    client = s3_client or create_s3_client()
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

        msg = f"Unexpected error while fetching file from S3: {bucket}/{key}. Error: {e.response['Error']['Message']}"
        raise Exception(msg) from e


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


def retrieve_opensearch_results(
    query: dict, index: str, opensearch_client: OpenSearch
) -> OpenSearchResult:
    """Retrieves search results from OpenSearch based on the provided query.

    :param query: The OpenSearch query to execute.
    :param index: The OpenSearch index to search.
    :param open_search_client: The OpenSearch client to use for the query.
    :return: The search results returned by OpenSearch.
    """
    response = opensearch_client.search(
        index=index,
        body=query,
    )

    return OpenSearchResult(**response)
