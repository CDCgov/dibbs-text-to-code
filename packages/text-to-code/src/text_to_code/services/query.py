import pydantic

from text_to_code.models.query import VectorSearchParams


class KNNQuery(pydantic.BaseModel):
    """Builds a KNN query."""

    field: str = pydantic.Field(
        default="descriptionVector", description="The field to perform the vector search on."
    )
    vector: list[float] = pydantic.Field(description="The vector to search for.")
    k: int = pydantic.Field(default=10, description="The number of nearest neighbors to retrieve.")

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

    def __init__(self):  # noqa: ANN204, D107
        self._must: list[dict] = []
        self._filters: list[dict] = []

    def with_knn(self, params: VectorSearchParams) -> "QueryBuilder":
        """Builds query with KNN.

        :param params: The parameters for the vector search.
        :return: The updated QueryBuilder instance.

        """
        query = KNNQuery(field=params.vector_field, vector=params.vector, k=params.k)
        self._must.append(query.to_opensearch())
        return self

    def with_terms_filter(self, params: VectorSearchParams) -> "QueryBuilder":
        """Adds a filter to the query.

        :param params: The parameters for the vector search.
        :return: The updated QueryBuilder instance.
        """
        filter = TermsFilter(field=params.filter_field, value=params.filter_value)
        self._filters.append(filter.to_opensearch())
        return self

    def with_vector_search(self, params: VectorSearchParams) -> "QueryBuilder":
        """Adds a vector search to the query based on the provided parameters.

        :param params: The parameters for the vector search.
        :return: The updated QueryBuilder instance.
        """
        self._size = params.size
        self.with_terms_filter(params)
        self.with_knn(params)
        self._vector_field = params.vector_field
        return self

    def build(self) -> dict:
        """Builds the final query dictionary.

        :return: The query as a dictionary.
        """
        return {
            "size": self._size,
            "_source": {
                "excludes": [self._vector_field]
            },  # Exclude the vector field from the results to reduce payload size & improve performance
            "query": {
                "bool": {
                    "filter": self._filters,
                    "must": self._must,
                }
            },
        }
