import typing

import pydantic

from text_to_code.models.eicr import DataField


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

    filter_value: list[str] | None = None

    @pydantic.model_validator(mode="after")
    def compute_filter_value(self) -> list[str]:
        """Uses the DataFieldTypeMapping to get the filter values corresponding to the data_field."""
        if self.filter_field == type(self).model_fields["filter_field"].default:
            self.filter_value = DataFieldTypeMapping.to_filter_values(self.data_field)
        else:
            raise ValueError(f"Unsupported filter field: {self.filter_field}")
        return self
