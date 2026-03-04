import os

import boto3
from opensearchpy import OpenSearch
from opensearchpy import RequestsHttpConnection
from requests_aws4auth import AWS4Auth


def _require_env(name: str) -> str:
    """Fetch a required environment variable or raise a clear error.

    :param name: The name of the environment variable to fetch.
    """
    value = os.getenv(name)
    if not value:
        raise ValueError(f"{name} not set")
    return value


def _strip_protocol(url: str) -> str:
    """Remove http/https from a URL.

    :param url: The URL to strip the protocol from.
    """
    return url.removeprefix("https://").removeprefix("http://")


def configure_opensearch_client() -> OpenSearch:
    """Configure the OpenSearch client using environment variables for authentication and connection details."""
    # Configuration set up
    region = _require_env("REGION")
    service = "es"
    host = _strip_protocol(_require_env("OPENSEARCH_ENDPOINT"))

    # Index name
    index_name = _require_env("INDEX_NAME")

    # Authentication
    credentials = boto3.Session().get_credentials()
    awsauth = AWS4Auth(
        credentials.access_key,
        credentials.secret_key,
        region,
        service,
        session_token=credentials.token,
    )

    # OpenSearch client
    os_client = OpenSearch(
        hosts=[{"host": host, "port": 443}],
        http_auth=awsauth,
        use_ssl=True,
        verify_certs=True,
        connection_class=RequestsHttpConnection,
    )
    return os_client, index_name


def lambda_handler(event: dict, context: dict) -> dict:
    """Lambda function to create an OpenSearch index with the appropriate mappings for storing LOINC code information and their corresponding vector embeddings.

    :param event: The event dict passed by AWS Lambda (not used in this function).
    :param context: The context dict passed by AWS Lambda (not used in this function).
    """
    # Create index with vectors mapping
    mapping = {
        "settings": {"index": {"number_of_shards": 1, "number_of_replicas": 1, "knn": True}},
        "mappings": {
            "properties": {
                "id": {"type": "keyword"},
                "description": {"type": "text"},
                "description_vector": {
                    "type": "knn_vector",
                    "dimension": 1024,
                    "method": {
                        "name": "hnsw",
                        "space_type": "cosinesimil",
                        "engine": "faiss",
                        "parameters": {"ef_construction": 128, "m": 16},
                    },
                },
                "loinc_type": {"type": "text"},
                "loinc_code": {"type": "text"},
                "loinc_name_type": {"type": "text"},
                "property": {"type": "keyword"},
                "time_aspect": {"type": "keyword"},
                "system": {"type": "keyword"},
                "scale_type": {"type": "keyword"},
                "method_type": {"type": "keyword"},
                "class_type": {"type": "keyword"},
                "type": {"type": "text"},
            },
        },
    }

    # Configure OpenSearch client
    os_client, index_name = configure_opensearch_client()

    # Create index if it doesn't already exist
    if not os_client.indices.exists(index=index_name):
        os_client.indices.create(index=index_name, body=mapping)

    # Check that index exists
    status = False
    if os_client.indices.exists(index=index_name):
        status = True

    # Check index mappings and settings
    settings = os_client.indices.get_settings(index=index_name)
    mappings = os_client.indices.get_mapping(index=index_name)

    # Check that description_vector field is in the mappings with knn_vector type
    recreated = False
    if (
        mappings[index_name]["mappings"]["properties"].get("description_vector", {}).get("type")
        != "knn_vector"
    ):
        # Delete the index if it was created but doesn't have the correct mappings
        os_client.indices.delete(index=index_name)
        # Recreate the index with the correct mappings
        os_client.indices.create(index=index_name, body=mapping)
        recreated = True

    return {
        "statusCode": 200,
        "index_exists": status,
        "index_settings": settings,
        "index_mappings": mappings,
        "index_recreated": recreated,
    }
