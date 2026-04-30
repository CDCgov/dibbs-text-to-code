from aws_lambda_powertools import Logger
from aws_lambda_powertools.utilities.typing import LambdaContext
from opensearchpy import OpenSearch

import lambda_handler
from utils import get_env_variable

logger = Logger(service="index-lambda")

INDEX_MAPPING = {
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
                    "parameters": {"ef_construction": 400, "m": 64},
                },
            },
            "loinc_type": {"type": "keyword"},
            "loinc_code": {"type": "keyword"},
            "loinc_name_type": {"type": "keyword"},
            "property": {"type": "keyword"},
            "time_aspect": {"type": "keyword"},
            "system": {"type": "keyword"},
            "scale_type": {"type": "keyword"},
            "method_type": {"type": "keyword"},
            "class_type": {"type": "keyword"},
        },
    },
}


@logger.inject_lambda_context
def handler(event: dict, context: LambdaContext) -> dict:
    """Lambda function to manage the OpenSearch index for LOINC code embeddings.

    Supports two actions via the event dict:
    - "clear_index": Deletes the existing index (if any) and recreates it empty.
      Use this before re-ingesting embeddings to avoid duplicates.
    - "create_index" (default): Creates the index only if it doesn't exist,
      and self-heals incorrect mappings.

    :param event: The event dict passed by AWS Lambda. Reads "action" key.
    :param context: The context dict passed by AWS Lambda (not used).
    """
    aws_auth = lambda_handler.create_aws_auth()
    os_client = lambda_handler.create_opensearch_client(aws_auth)
    index_name = get_env_variable("INDEX_NAME")

    action = event.get("action", "create_index") if event else "create_index"

    with logger.append_context_keys(
        index_name=index_name,
        action=action,
    ):
        logger.info("Index Lambda started", status="processing")

        if action == "clear_index":
            result = _clear_index(os_client, index_name)
        elif action == "set_slowlog":
            result = _set_slowlog(os_client, index_name, event.get("threshold_ms", 0))
        else:
            result = _create_index(os_client, index_name)

        logger.info("Index Lambda completed", status="success")

        return result


def _clear_index(os_client: OpenSearch, index_name: str) -> dict:
    """Delete the index if it exists, then recreate it with correct mappings.

    :param os_client: The OpenSearch client
    :param index_name: The name of the index
    """
    deleted = False
    if os_client.indices.exists(index=index_name):
        os_client.indices.delete(index=index_name)
        deleted = True

    os_client.indices.create(index=index_name, body=INDEX_MAPPING)

    logger.info(
        "OpenSearch index cleared",
        index_deleted=deleted,
        index_recreated=True,
        status="success",
    )

    return {
        "statusCode": 200,
        "action": "clear_index",
        "index_deleted": deleted,
        "index_recreated": True,
    }


def _set_slowlog(os_client: OpenSearch, index_name: str, threshold_ms: int) -> dict:
    index = os_client.indices.get(index=index_name)
    settings = os_client.indices.get_settings(index=index_name)
    mappings = os_client.indices.get_mapping(index=index_name)

    threshold = f"{threshold_ms}ms" if threshold_ms > 0 else "-1"
    body = {
        "index.search.slowlog.threshold.query.warn": threshold,
        "index.search.slowlog.threshold.query.info": threshold,
        "index.search.slowlog.threshold.fetch.warn": threshold,
        "index.search.slowlog.threshold.fetch.info": threshold,
    }
    os_client.indices.put_settings(index=index_name, body=body)

    logger.info(
        "OpenSearch slowlog settings updated",
        threshold_ms=threshold_ms,
        status="success",
    )

    return {
        "statusCode": 200,
        "action": "set_slowlog",
        "threshold_ms": threshold_ms,
        "index": index,
        "settings": settings,
        "mappings": mappings,
    }


def _create_index(os_client: OpenSearch, index_name: str) -> dict:
    """Create the index if it doesn't exist, self-healing incorrect mappings.

    :param os_client: The OpenSearch client
    :param index_name: The name of the index
    """
    if not os_client.indices.exists(index=index_name):
        os_client.indices.create(index=index_name, body=INDEX_MAPPING)
        logger.info("OpenSearch index created", status="success")

    status = os_client.indices.exists(index=index_name)

    settings = os_client.indices.get_settings(index=index_name)
    mappings = os_client.indices.get_mapping(index=index_name)

    recreated = False
    if (
        mappings[index_name]["mappings"]["properties"].get("description_vector", {}).get("type")
        != "knn_vector"
    ):
        os_client.indices.delete(index=index_name)
        os_client.indices.create(index=index_name, body=INDEX_MAPPING)
        recreated = True

    logger.info(
        "OpenSearch index validated",
        index_exists=status,
        index_recreated=recreated,
        status="success",
    )

    return {
        "statusCode": 200,
        "index_exists": status,
        "index_settings": settings,
        "index_mappings": mappings,
        "index_recreated": recreated,
    }
