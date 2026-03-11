import typing

import pydantic
from shared_models import DataField


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


class VectorSearchParams(pydantic.BaseModel):
    """Parameters for performing a vector search."""

    vector: list[float] = pydantic.Field(description="The vector to search for.")
    vector_field: str = pydantic.Field(
        default="descriptionVector", description="The field to perform the vector search on."
    )
    filter_field: str = pydantic.Field(
        default="type", description="The field to filter on, e.g., 'type'."
    )
    data_field: DataField = pydantic.Field(
        description="The value of the field to filter on, e.g., 'Lab Test Name Ordered' or 'Lab Test Name Resulted'."
    )
    size: int = pydantic.Field(default=10, description="The number of results to retrieve.")
    k: int = pydantic.Field(
        default=10, description="The number of nearest neighbors to examine during the query."
    )
    filter_value: list[str] = pydantic.Field(
        default_factory=list,
        init=False,
        description="The list of filter values corresponding to the data_field, computed after initialization.",
    )

    @pydantic.model_validator(mode="after")
    def compute_filter_value(self) -> "VectorSearchParams":
        """Uses the DataFieldTypeMapping to get the filter values corresponding to the data_field."""
        if self.filter_field == type(self).model_fields["filter_field"].default:
            self.filter_value = DataFieldTypeMapping.to_filter_values(self.data_field)
        else:
            raise ValueError(f"Unsupported filter field: {self.filter_field}")
        return self


class S3Location(pydantic.BaseModel):
    """Represents the location of a file in S3, indicating which file contained the relevant data."""

    bucket: str
    key: str


class OpenSearchHit(pydantic.BaseModel):
    """Represents a single search result hit returned from OpenSearch."""

    score: float
    id: int
    loinc_code: str
    loinc_name_type: str
    description: str
    loinc_type: str
    s3: S3Location


class OpenSearchHits(pydantic.BaseModel):
    """Represents all of the search result hits returned from OpenSearch."""

    total_hits: int
    hits: list[OpenSearchHit]


class OpenSearchShards(pydantic.BaseModel):
    """Represents the shard information returned from OpenSearch."""

    total: int
    successful: int
    skipped: int
    failed: int


class OpenSearchResult(pydantic.BaseModel):
    """Represents the overall search result returned from OpenSearch, including hits and shard information."""

    took: int
    timed_out: bool
    _shards: OpenSearchShards
    hits: OpenSearchHits
