import pydantic

from text_to_code.models.query import VectorSearchParams


class KNNQuery(pydantic.BaseModel):
    """Builds a KNN query."""

    field: str
    vector: list[float]
    k: int = 10

    def to_opensearch(self) -> dict:
        """Builds an OpenSearch-specific KNN query."""
        return {
            "knn": {
                self.field: {
                    "vector": self.vector,
                    "k": self.k,
                }
            }
        }


class TermsFilter(pydantic.BaseModel):
    """Builds a terms filter for the query."""

    field: str = pydantic.Field(default="type", description="The field to filter on, e.g., 'type'.")
    value: list[str] = pydantic.Field(
        description="The value(s) to filter the specified field by, e.g., ['order','both'] or ['observation', 'both']."
    )

    def to_opensearch(self) -> dict:
        """Builds an OpenSearch-specific terms filter."""
        return {"terms": {self.field: self.value}}


class QueryBuilder:
    """Builds a query with filters and KNN queries."""

    def __init__(self, size: int = 10):  # noqa: D107
        self.size = size
        self._must: list[dict] = []
        self._filters: list[dict] = []

    def with_knn(self, field: str, vector: list[float], k: int) -> "QueryBuilder":
        """Builds query with KNN.

        :param field: The field to perform KNN on, e.g., "descriptionVector".
        :param vector: The vector to search with.
        :param k: The number of nearest neighbors to retrieve.
        :return: The updated QueryBuilder instance.

        """
        query = KNNQuery(field=field, vector=vector, k=k)
        self._must.append(query.to_opensearch())
        return self

    def with_terms_filter(self, field: str, value: list[str]) -> "QueryBuilder":
        """Adds a filter to the query.

        :param field: The field to filter on.
        :param value: The value to filter by.
        :return: The updated QueryBuilder instance.
        """
        filter = TermsFilter(field=field, value=value)
        self._filters.append(filter.to_opensearch())
        return self

    def with_vector_search(self, params: VectorSearchParams) -> "QueryBuilder":
        """Adds a vector search to the query based on the provided parameters.

        :param params: The parameters for the vector search.
        :return: The updated QueryBuilder instance.
        """
        self._size = params.size
        self.with_terms_filter(field=params.filter_field, value=params.filter_value)
        self.with_knn(field=params.vector_field, vector=params.vector, k=params.k)
        return self

    def build(self) -> dict:
        """Builds the final query dictionary.

        :return: The query as a dictionary.
        """
        return {
            "size": self._size,
            "query": {
                "bool": {
                    "filter": self._filters,
                    "must": self._must,
                }
            },
        }
