import os

from opensearchpy import OpenSearch
from opensearchpy import RequestsHttpConnection


def test_opensearch_container_functionality():
    opensearch_pwd = os.environ.get("OPENSEARCH_PWD", "TEST_PSWD!")
    # Configuration for your OpenSearch instance
    host = "opensearch-net"
    port = 9200
    auth = ("admin", opensearch_pwd)

    # Initialize the OpenSearch client
    client = OpenSearch(
        hosts=[{"host": host, "port": port}],
        http_auth=auth,
        use_ssl=False,  # Set to False if not using SSL/TLS
        verify_certs=False,  # Set to True in production with valid certificates
        connection_class=RequestsHttpConnection,
    )

    # 1. Check cluster health
    health = client.cluster.health()
    assert health["status"] in ["green", "yellow"], (
        f"OpenSearch cluster health is {health['status']}"
    )

    # 2. Create an index
    index_name = "test_index"
    if client.indices.exists(index=index_name):
        client.indices.delete(index=index_name)  # Clean up if index exists
    response = client.indices.create(index=index_name)
    assert response["acknowledged"] is True, "Failed to create index."

    # 3. Add a document
    document = {"title": "Test Document", "content": "This is a test document."}
    response = client.index(
        index=index_name, id="1", body=document, refresh=True
    )  # refresh=True makes it immediately searchable
    assert response["result"] == "created", "Failed to add document."

    # 4. Search for the document
    search_body = {"query": {"match": {"title": "Test"}}}
    response = client.search(index=index_name, body=search_body)
    assert response["hits"]["total"]["value"] == 1, "Search did not find the expected document."
    assert response["hits"]["hits"][0]["_source"]["title"] == "Test Document", (
        "Search found incorrect document."
    )

    # 5. Clean up indices and documents
    client.indices.delete(index=index_name)
