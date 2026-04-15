from opensearchpy import OpenSearch

import lambda_handler

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


def handler(event: dict, context: dict) -> dict:
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
    index_name = lambda_handler.require_env("INDEX_NAME")

    action = event.get("action", "create_index") if event else "create_index"

    if action == "clear_index":
        return _clear_index(os_client, index_name)
    return _create_index(os_client, index_name)


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

    return {
        "statusCode": 200,
        "action": "clear_index",
        "index_deleted": deleted,
        "index_recreated": True,
    }


def _create_index(os_client: OpenSearch, index_name: str) -> dict:
    """Create the index if it doesn't exist, self-healing incorrect mappings.

    :param os_client: The OpenSearch client
    :param index_name: The name of the index
    """
    if not os_client.indices.exists(index=index_name):
        os_client.indices.create(index=index_name, body=INDEX_MAPPING)

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

    return {
        "statusCode": 200,
        "index_exists": status,
        "index_settings": settings,
        "index_mappings": mappings,
        "index_recreated": recreated,
    }
