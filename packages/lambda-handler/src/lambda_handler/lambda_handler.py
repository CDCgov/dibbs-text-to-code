import os
from typing import BinaryIO

import boto3
from aws_lambda_powertools import Logger
from aws_lambda_typing import events as lambda_events
from botocore.client import BaseClient
from botocore.config import Config
from botocore.credentials import Credentials
from botocore.exceptions import ClientError
from opensearchpy import OpenSearch, RequestsHttpConnection
from requests_aws4auth import AWS4Auth

from lambda_handler.models.opensearch import OpenSearchHitSource
from utils import get_env_variable

from .models import OpenSearchHit, OpenSearchHits, OpenSearchResult

logger = Logger(service="lambda-handler", child=True)

_cached_aws_auth: AWS4Auth | None = None
_cached_s3_client: BaseClient | None = None
_cached_opensearch_client: OpenSearch | None = None

# Without explicit timeouts a stalled connection blocks until the Lambda
# itself times out (up to 900s); bound each call well below that instead.
_S3_CLIENT_CONFIG = Config(
    connect_timeout=5,
    read_timeout=60,
    retries={"mode": "adaptive", "max_attempts": 3},
)
_OPENSEARCH_TIMEOUT_SECONDS = 30
_OPENSEARCH_MAX_RETRIES = 2


def reset_cached_clients() -> None:
    """Reset cached AWS clients and auth. This is useful for testing to ensure that environment variable changes are picked up."""
    global _cached_aws_auth  # noqa: PLW0603
    global _cached_s3_client  # noqa: PLW0603
    global _cached_opensearch_client  # noqa: PLW0603

    _cached_aws_auth = None
    _cached_s3_client = None
    _cached_opensearch_client = None


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

    if _cached_aws_auth is None:
        credentials = get_s3_credentials()
        _cached_aws_auth = AWS4Auth(
            credentials.access_key,
            credentials.secret_key,
            get_env_variable("AWS_REGION"),
            "es",
            session_token=credentials.token,
        )
        logger.info("Created AWS auth", status="success")

    return _cached_aws_auth


def create_s3_client() -> BaseClient:
    """Creates an S3 client.

    :return: S3 client
    """
    global _cached_s3_client  # noqa: PLW0603

    if _cached_s3_client is None:
        endpoint_url = os.getenv("S3_ENDPOINT_URL")
        region_name = get_env_variable("AWS_REGION")
        _cached_s3_client = boto3.client(
            "s3",
            endpoint_url=endpoint_url,
            region_name=region_name,
            config=_S3_CLIENT_CONFIG,
        )
        logger.info("Created S3 client", status="success")

    return _cached_s3_client


def create_opensearch_client() -> OpenSearch:
    """Creates an OpenSearch client.

    :param aws_auth: AWS4Auth object for authentication
    :return: OpenSearch client
    """
    global _cached_opensearch_client  # noqa: PLW0603

    if _cached_opensearch_client is None:
        endpoint_url = get_env_variable("OPENSEARCH_ENDPOINT_URL")
        auth = create_aws_auth()
        _cached_opensearch_client = OpenSearch(
            hosts=[{"host": strip_protocol(endpoint_url), "port": 443}],
            http_auth=auth,
            use_ssl=True,
            verify_certs=True,
            connection_class=RequestsHttpConnection,
            timeout=_OPENSEARCH_TIMEOUT_SECONDS,
            max_retries=_OPENSEARCH_MAX_RETRIES,
            retry_on_timeout=True,
        )
        logger.info("Created OpenSearch client", status="success")

    return _cached_opensearch_client


def get_file_content_from_s3(bucket_name: str, object_key: str) -> str:
    """Extracts the file content from an S3 bucket.

    :param bucket_name: The name of the S3 bucket.
    :param object_key: The key of the S3 object.
    :return: The content of the file as a string.
    """
    client = create_s3_client()

    logger.info(
        "Retrieving file content from S3",
        bucket_name=bucket_name,
        s3_key=object_key,
        status="processing",
    )

    try:
        response = client.get_object(Bucket=bucket_name, Key=object_key)
    except ClientError as e:
        # GET reports a missing key as NoSuchKey (HEAD reports 404); a
        # pre-flight existence check would double the round trips, so map
        # the GET error to the same FileNotFoundError callers rely on.
        if e.response["Error"]["Code"] in ("404", "NoSuchKey"):
            logger.warning(
                "S3 object not found",
                bucket_name=bucket_name,
                s3_key=object_key,
                status="error",
            )
            raise FileNotFoundError(f"S3 object not found: {bucket_name}/{object_key}") from e
        raise
    logger.info(
        "Retrieved file content from S3",
        bucket_name=bucket_name,
        s3_key=object_key,
        status="success",
    )
    return response["Body"].read().decode("utf-8")


def get_eventbridge_data_from_s3_event(event: lambda_events.EventBridgeEvent) -> dict:
    """Extracts the file metadata from an S3 event triggered by a Lambda function.

    :param event: The S3 event containing the bucket and object key information.
    :return: A dictionary containing the bucket name and object key.
    """
    bucket_name = event.get("detail", {}).get("bucket", {}).get("name")
    object_key = event["detail"]["object"]["key"]

    logger.info(
        "Extracted EventBridge S3 event data",
        bucket_name=bucket_name,
        s3_key=object_key,
        status="success",
    )

    return {"bucket_name": bucket_name, "object_key": object_key}


def put_file(file_obj: BinaryIO, bucket_name: str, object_key: str) -> None:
    """Uploads a file object to a S3 bucket.

    :param file_obj: The file object to upload.
    :param bucket_name: The name of the S3 bucket to upload to.
    :param object_key: The key to assign to the uploaded object in S3.
    """
    client = create_s3_client()
    logger.info(
        "Uploading file to S3",
        bucket_name=bucket_name,
        s3_key=object_key,
        status="processing",
    )
    client.put_object(Body=file_obj, Bucket=bucket_name, Key=object_key)
    logger.info(
        "Uploaded file to S3",
        bucket_name=bucket_name,
        s3_key=object_key,
        status="success",
    )


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
        logger.info("S3 object exists", bucket_name=bucket, s3_key=key, status="success")
        return True
    except ClientError as e:
        error_code = e.response["Error"]["Code"]

        if error_code in ("404", "NoSuchKey"):
            logger.warning(
                "S3 object does not exist", bucket_name=bucket, s3_key=key, status="error"
            )
            return False

        msg = f"Unexpected error while fetching file from S3: {bucket}/{key}. Error: {e.response['Error']['Message']}"
        logger.exception(
            "Unexpected error while fetching file from S3",
            bucket_name=bucket,
            s3_key=key,
            error=e.response["Error"]["Message"],
            status="error",
        )
        raise Exception(msg) from e


def get_persistence_id(object_key: str, input_prefix: str) -> str:
    """Get the persistence_id from an S3 object key.

    Object key format: <pipeline-step>/<persistance_id>
    Example: TextToCodeSubmissionV2/2026/01/01/0026b704-f510-4494-8d21-11d27217d96e
    Returns: 2026/01/01/0026b704-f510-4494-8d21-11d27217d96e

    :param object_key: The S3 object key
    :param input_prefix: The pipeline step prefix (e.g., "TextToCodeSubmissionV2/")
    :return: The persistence_id portion of the key

    """
    if not object_key.startswith(input_prefix):
        logger.error(
            "S3 object key does not start with expected prefix",
            s3_key=object_key,
            input_prefix=input_prefix,
            status="error",
        )
        raise ValueError(
            f"Object key '{object_key}' does not start with expected prefix '{input_prefix}'"
        )
    persistence_id = object_key[len(input_prefix) :]
    logger.info(
        "Extracted persistence_id from S3 object key",
        s3_key=object_key,
        persistence_id=persistence_id,
        status="success",
    )
    return persistence_id


def retrieve_opensearch_results(
    query: dict, index: str, opensearch_client: OpenSearch
) -> OpenSearchResult:
    """Retrieves search results from OpenSearch based on the provided query.

    :param query: The OpenSearch query to execute.
    :param index: The OpenSearch index to search.
    :param opensearch_client: The OpenSearch client to use for the query.
    :return: The search results returned by OpenSearch.
    """
    logger.info(
        "Retrieving OpenSearch results",
        index=index,
        status="processing",
    )
    response = opensearch_client.search(
        index=index,
        body=query,
    )
    logger.info(
        "Retrieved OpenSearch results",
        index=index,
        status="success",
    )

    hits_json = response["hits"]
    hits = OpenSearchHits(
        total=hits_json["total"],
        hits=[
            OpenSearchHit(
                _index=hit["_index"],
                _id=hit["_id"],
                _score=hit["_score"],
                _source=OpenSearchHitSource(
                    id=hit["_source"]["id"],
                    loinc_code=hit["_source"]["loinc_code"],
                    loinc_name_type=hit["_source"]["loinc_name_type"],
                    description=hit["_source"]["description"],
                    loinc_type=hit["_source"]["loinc_type"],
                ),
            )
            for hit in hits_json["hits"]
        ],
    )

    return OpenSearchResult(
        took=response["took"],
        timed_out=response["timed_out"],
        _shards=response["_shards"],
        hits=hits,
    )
