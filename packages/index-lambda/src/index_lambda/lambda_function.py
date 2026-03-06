import s3_handler


def handler(event: dict, context: dict) -> dict:
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

    # Configure OpenSearch client
    aws_auth = s3_handler.create_aws_auth()
    os_client = s3_handler.create_opensearch_client(aws_auth)
    index_name = s3_handler.require_env("INDEX_NAME")

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
