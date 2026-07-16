from pydantic import Field

from shared_models import FrozenBaseModel
from text_to_code.models.query import VectorSearchParams


class KNNQuery(FrozenBaseModel):
    """Builds a KNN query."""

    field: str = Field(
        default="description_vector", description="The field to perform the vector search on."
    )
    vector: list[float] = Field(description="The vector to search for.")
    k: int = Field(default=10, description="The number of nearest neighbors to retrieve.")

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


class TermsFilter(FrozenBaseModel):
    """Builds a terms filter for the query.

    The filter narrows down the search results to only include documents where the
    specified field matches one of the provided values, ensuring that TTC retrieves
    codes relevant to the specific data field. That is, it only returns LOINC codes
    of type "Order" or "Both" for the lab test name ordered data field, and only LOINC
    codes of type "Observation" or "Both" for the lab test result data field.
    """

    field: str = Field(
        default="loinc_type", description="The field to filter on, e.g., 'loinc_type'."
    )
    value: list[str] = Field(
        description="The value(s) to filter the specified field by, e.g., ['order','both'] or ['observation', 'both']."
    )

    def to_opensearch(self) -> dict:
        """Builds an OpenSearch-specific terms filter."""
        return {"terms": {self.field: self.value}}


class QueryBuilder:
    """Builds a query with filters and KNN queries."""

    def __init__(self) -> None:
        """Initialize query builder."""
        self._must: list[dict] = []
        self._filters: list[dict] = []

    def with_knn(self, params: VectorSearchParams) -> QueryBuilder:
        """Builds query with KNN.

        :param params: The parameters for the vector search.
        :return: The updated QueryBuilder instance.

        """
        query = KNNQuery(field=params.vector_field, vector=params.vector, k=params.k)
        self._must.append(query.to_opensearch())
        return self

    def with_terms_filter(self, params: VectorSearchParams) -> QueryBuilder:
        """Adds a filter to the query.

        :param params: The parameters for the vector search.
        :return: The updated QueryBuilder instance.
        """
        filter = TermsFilter(field=params.filter_field, value=params.filter_value)
        self._filters.append(filter.to_opensearch())
        return self

    def with_vector_search(self, params: VectorSearchParams) -> QueryBuilder:
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
                "excludes": [
                    self._vector_field
                ],  # Exclude the vector field from the results to reduce payload size & improve performance
                "includes": ["id", "loinc_code", "loinc_name_type", "description", "loinc_type"],
            },
            "query": {
                "bool": {
                    "filter": self._filters,
                    "must": self._must,
                }
            },
        }
