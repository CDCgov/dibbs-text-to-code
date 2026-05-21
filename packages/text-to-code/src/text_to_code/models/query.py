import typing

from pydantic import Field, model_validator

from shared_models import DataField, FrozenBaseModel


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


class VectorSearchParams(FrozenBaseModel):
    """Parameters for performing a vector search."""

    vector: list[float] = Field(description="The vector to search for.")
    vector_field: str = Field(
        default="description_vector", description="The field to perform the vector search on."
    )
    filter_field: str = Field(
        default="loinc_type", description="The field to filter on, e.g., 'loinc_type'."
    )
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
            # We have to use `object.__setattr__` because this is a frozen model.
            object.__setattr__(
                self, "filter_value", DataFieldTypeMapping.to_filter_values(self.data_field)
            )
        else:
            raise ValueError(f"Unsupported filter field: {self.filter_field}")

        return self
