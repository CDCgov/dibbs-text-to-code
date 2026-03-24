import typing

from pydantic import BaseModel
from pydantic import Field
from pydantic import model_validator

from shared_models import DataField
from shared_models import OpenSearchHitSource


class DataFieldTypeMapping:
    """Mapping of DataField enum values to their corresponding filter values for vector search."""

    _mapping: typing.ClassVar[dict[DataField, list[str]]] = {
        DataField.LAB_TEST_NAME_ORDERED: ["Order", "Both"],
        DataField.LAB_TEST_NAME_RESULTED: ["Observation", "Both"],
    }

    @classmethod
    def to_filter_values(cls, data_field: DataField) -> list[str]:
        """Returns the list of filter values corresponding to the given DataField enum value."""
        try:
            return cls._mapping[data_field]
        except KeyError as err:
            raise ValueError(f"No type mapping defined for {data_field}") from err


class VectorSearchParams(BaseModel):
    """Parameters for performing a vector search."""

    vector: list[float] = Field(description="The vector to search for.")
    vector_field: str = Field(
        default="descriptionVector", description="The field to perform the vector search on."
    )
    filter_field: str = Field(default="type", description="The field to filter on, e.g., 'type'.")
    data_field: DataField = Field(
        description="The value of the field to filter on, e.g., 'Lab Test Name Ordered' or 'Lab Test Name Resulted'."
    )
    size: int = Field(default=10, description="The number of results to retrieve.")
    k: int = Field(
        default=10, description="The number of nearest neighbors to examine during the query."
    )
    filter_value: list[str] = Field(
        default_factory=list,
        init=False,
        description="The list of filter values corresponding to the data_field, computed after initialization.",
    )

    @model_validator(mode="after")
    def compute_filter_value(self) -> "VectorSearchParams":
        """Uses the DataFieldTypeMapping to get the filter values corresponding to the data_field."""
        if self.filter_field == type(self).model_fields["filter_field"].default:
            self.filter_value = DataFieldTypeMapping.to_filter_values(self.data_field)
        else:
            raise ValueError(f"Unsupported filter field: {self.filter_field}")
        return self


class OpenSearchHit(BaseModel):
    """Represents a single search result hit returned from OpenSearch."""

    index: str = Field(
        description="The index that the search result hit came from.", alias="_index"
    )
    id: str = Field(description="The unique OpenSearch ID of the search result hit.", alias="_id")
    score: float = Field(
        description="The cosine similarity score of the search result hit.", alias="_score"
    )
    source: OpenSearchHitSource = Field(
        description="The source of the search result hit.", alias="_source"
    )


class OpenSearchHits(BaseModel):
    """Represents all of the search result hits returned from OpenSearch."""

    total_hits: dict[str, int] = Field(
        alias="total", description="The total number of hits returned from OpenSearch."
    )
    hits: list[OpenSearchHit] = Field(
        description="The list of search result hits returned from OpenSearch."
    )


class OpenSearchShards(BaseModel):
    """Represents the shard information returned from OpenSearch."""

    total: int = Field(description="The total number of shards involved in the search.")
    successful: int = Field(description="The number of shards that successfully returned results.")
    skipped: int = Field(description="The number of shards that were skipped during the search.")
    failed: int = Field(description="The number of shards that failed to return results.")


class OpenSearchResult(BaseModel):
    """Represents the overall search result returned from OpenSearch, including hits and shard information."""

    took: int = Field(description="The time taken to execute the search in milliseconds.")
    timed_out: bool = Field(description="Indicates whether the search timed out.")
    shards: OpenSearchShards = Field(
        description="The shard information for the search.", alias="_shards"
    )
    hits: OpenSearchHits = Field(description="The search result hits returned from OpenSearch.")
