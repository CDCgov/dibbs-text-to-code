import typing

import pydantic


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


class TermFilter(pydantic.BaseModel):
    """Builds a term filter for the query."""

    field: str = "type"
    value: typing.Literal["Order", "Observation", "Both"]

    def to_opensearch(self) -> dict:
        """Builds an OpenSearch-specific term filter."""
        return {"term": {self.field: self.value}}


class QueryBuilder:
    """Builds a query with filters and KNN queries."""

    def __init__(self, size: int = 10):  # noqa: D107
        self.size = size
        self._must = list[dict] = []
        self._filters = list[dict] = []

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

    def with_filter(self, field: str, value: str) -> "QueryBuilder":
        """Adds a filter to the query.

        :param field: The field to filter on.
        :param value: The value to filter by.
        :return: The updated QueryBuilder instance.
        """
        filter = TermFilter(field=field, value=value)
        self._filters.append(filter.to_opensearch())
        return self

    def build(self) -> dict:
        """Builds the final query dictionary.

        :return: The query as a dictionary.
        """
        return {
            "size": self.size,
            "query": {
                "bool": {
                    "filter": self._filters,
                    "must": self._must,
                }
            },
        }


# query = (
#     QueryBuilder(size=10)
#     .with_filter("type", dtype)
#     .with_knn("descriptionVector", vector, k)
#     .build()
# )
