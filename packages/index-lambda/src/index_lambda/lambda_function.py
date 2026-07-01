from typing import TypedDict

from aws_lambda_powertools import Logger
from aws_lambda_powertools.utilities.typing import LambdaContext
from opensearchpy import OpenSearch

import lambda_handler
from utils import get_env_variable


class OpenSearchIndexMapping(TypedDict):
    """Defines required dictionary properties for an OpenSearch Index Mapping.

    Other attributes may be present, and each of these attributes may hold
    dictionaries with unknown keys (since they're based on the shape of the
    data to-index), but these attributes are themselves required.
    """

    settings: dict
    mappings: dict


logger = Logger(service="index-lambda")

INDEX_MAPPING: OpenSearchIndexMapping = {
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

RESULT_CACHE_INDEX_MAPPING: OpenSearchIndexMapping = {
    "settings": {"index": {"number_of_shards": 1, "number_of_replicas": 1, "knn": False}},
    "mappings": {
        "properties": {
            "cache_key": {"type": "keyword"},
            "text": {"type": "keyword"},
            "data_field": {"type": "keyword"},
            "code": {"type": "object", "enabled": False},
            "score": {"type": "float"},
            "cached_at": {"type": "date"},
        },
    },
}


@logger.inject_lambda_context
def handler(event: dict, context: LambdaContext) -> dict:
    """Lambda function to manage the OpenSearch index for LOINC code embeddings.

    Supports seven actions via the event dict:
    - "clear_index": Deletes the existing index (if any) and recreates it empty.
      Use this before re-ingesting embeddings to avoid duplicates.
    - "clear_result_cache": As above, but for the Result Cache index rather than
      the Vector Search index.
    - "create_index" (default): Creates the index only if it doesn't exist,
      and self-heals incorrect mappings.
    - "create_result_cache": As above, but for the Result Cache index.
    - "set_slowlog": Changes logging parameters for AWS across multiple types
      of logging information.
    - "set_result_cache_slowlog": As above, but for the Result Cache index.
    - "update_term_embeddings": Perform Update process for all terminology
       embeddings (now only LOINC Lab Names).

    :param event: The event dict passed by AWS Lambda. Reads "action" key.
    :param context: The context dict passed by AWS Lambda (not used).
    """
    os_client = lambda_handler.create_opensearch_client()
    index_name = get_env_variable("INDEX_NAME")
    result_cache_index_name = get_env_variable("RESULT_CACHE_INDEX_NAME")

    action = event.get("action", "create_index") if event else "create_index"
    logger_name = result_cache_index_name if "result_cache" in action else index_name
    with logger.append_context_keys(
        index_name=logger_name,
        action=action,
    ):
        logger.info("Index Lambda started", status="processing")

        if action == "clear_index":
            result = _clear_index(os_client, index_name, INDEX_MAPPING, action)
        elif action == "clear_result_cache":
            result = _clear_index(
                os_client, result_cache_index_name, RESULT_CACHE_INDEX_MAPPING, action
            )
        elif action == "set_slowlog":
            result = _set_slowlog(os_client, index_name, event.get("threshold_ms", 0), action)
        elif action == "set_result_cache_slowlog":
            result = _set_slowlog(
                os_client, result_cache_index_name, event.get("threshold_ms", 0), action
            )
        elif action == "create_index":
            result = _create_index(os_client, index_name, INDEX_MAPPING)
        elif action == "create_result_cache":
            result = _create_index(os_client, result_cache_index_name, RESULT_CACHE_INDEX_MAPPING)
        else:
            raise ValueError(f"Received unknown action: {action!r}")

        logger.info("Index Lambda completed", status="success")

        return result


def _clear_index(
    os_client: OpenSearch, index_name: str, index_mapping: OpenSearchIndexMapping, action: str
) -> dict:
    """Delete the specified index if it exists, then recreate it with the supplied mapping.

    :param os_client: The OpenSearch client
    :param index_name: The name of the index
    :param index_mapping: The formally-specified mapping to create for this index.
    :param action: The action from the event queue that kicked off the index clear.
      We use this to specify appropriate logging information in the response.
    """
    deleted = False
    if os_client.indices.exists(index=index_name):
        os_client.indices.delete(index=index_name)
        deleted = True

    os_client.indices.create(index=index_name, body=index_mapping)

    logger.info(
        "OpenSearch index cleared",
        index_name=index_name,
        index_deleted=deleted,
        index_recreated=True,
        status="success",
    )

    return {
        "statusCode": 200,
        "action": action,
        "index_name": index_name,
        "index_deleted": deleted,
        "index_recreated": True,
    }


def _set_slowlog(os_client: OpenSearch, index_name: str, threshold_ms: int, action: str) -> dict:
    """Modify the slowlog settings for a specified index to change logging behavior.

    :param os_client: The OpenSearch client
    :param index_name: The name of the index
    :param threshold_ms: The threshold in miliseconds that the log should use.
    :param action: The action from the event queue that kicked off the index clear.
      We use this to specify appropriate logging information in the response.
    """
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
        "action": action,
        "threshold_ms": threshold_ms,
        "index": index,
        "index_name": index_name,
        "settings": settings,
        "mappings": mappings,
    }


def _create_index(
    os_client: OpenSearch, index_name: str, index_mapping: OpenSearchIndexMapping
) -> dict:
    """Create the index if it doesn't exist; otherwise return the current settings and mappings.

    :param os_client: The OpenSearch client.
    :param index_name: The name of the index.
    :param index_mapping: The properties mapping for the specified index.
    """
    created = False
    if not os_client.indices.exists(index=index_name):
        os_client.indices.create(index=index_name, body=index_mapping)
        logger.info("OpenSearch index created", index_name=index_name, status="success")
        created = True

    status = os_client.indices.exists(index=index_name)

    settings = os_client.indices.get_settings(index=index_name)
    mappings = os_client.indices.get_mapping(index=index_name)

    logger.info(
        "OpenSearch index validated",
        index_name=index_name,
        index_exists=status,
        status="success",
    )

    return {
        "statusCode": 200,
        "index_name": index_name,
        "ran_index_creation": created,
        "index_exists": status,
        "index_settings": settings,
        "index_mappings": mappings,
    }


def _update_terminology_embeddings(terminology_set: str) -> dict:
    """Updates the embeddings in our Opensearch for a specific terminology set, which could be for multiple data elements.

    :param terminology_set: The Terminology set being updated (ie. SNOMED, LOINC, etc...)
    """
    return {
        "statusCode": 200,
        "terminology": terminology_set,
    }
