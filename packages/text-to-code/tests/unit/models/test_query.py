import pydantic
import pytest

from shared_models import DataField
from text_to_code.models import VectorSearchParams
from text_to_code.models.query import DataFieldTypeMapping


class TestDataFieldTypeMapping:
    def test_to_filter_values_valid_data_field(self):
        """Tests that the correct filter values are returned for valid DataField enum values."""
        assert DataFieldTypeMapping.to_filter_values(DataField.LAB_TEST_NAME_ORDERED) == [
            "Order",
            "Both",
        ]
        assert DataFieldTypeMapping.to_filter_values(DataField.LAB_TEST_NAME_RESULTED) == [
            "Observation",
            "Both",
        ]

    def test_to_filter_values_invalid_data_field(self):
        """Tests that a ValueError is raised for an invalid DataField enum value."""
        with pytest.raises(ValueError, match="No type mapping defined for invalid_value"):
            DataFieldTypeMapping.to_filter_values("invalid_value")


class TestVectorSearchParams:
    def test_vector_search_params_with_defaults(self):
        """Tests that default values are correctly set in the VectorSearchParams model."""
        vector = [0.1, 0.2, 0.3]
        data_field = DataField.LAB_TEST_NAME_RESULTED
        params = VectorSearchParams(
            vector=vector,
            data_field=data_field,
        )
        assert isinstance(params, VectorSearchParams)
        assert params.vector == [0.1, 0.2, 0.3]
        assert params.filter_value == ["Observation", "Both"]
        assert params.vector_field == VectorSearchParams.model_fields["vector_field"].default
        assert params.filter_field == VectorSearchParams.model_fields["filter_field"].default
        assert params.size == VectorSearchParams.model_fields["size"].default
        assert params.k == VectorSearchParams.model_fields["k"].default

    def test_vector_search_params_with_custom_values(self):
        """Tests that custom values for all fields are correctly set in the VectorSearchParams model."""
        vector = [0.1, 0.2, 0.3]
        data_field = DataField.LAB_TEST_NAME_ORDERED
        size = 5
        k = 3
        custom_vector_field = "custom_vector_field"
        custom_filter_field = "loinc_type"
        params = VectorSearchParams(
            vector=vector,
            data_field=data_field,
            vector_field=custom_vector_field,
            filter_field=custom_filter_field,
            size=size,
            k=k,
        )
        assert isinstance(params, VectorSearchParams)
        assert params.vector == [0.1, 0.2, 0.3]
        assert params.vector_field == custom_vector_field
        assert params.filter_field == custom_filter_field
        assert params.filter_value == DataFieldTypeMapping.to_filter_values(data_field)
        assert params.size == size
        assert params.k == k

    def test_vector_search_params_with_invalid_filter_field(self):
        """Tests that an invalid filter field raises a ValueError in the VectorSearchParams model."""
        vector = [0.1, 0.2, 0.3]
        data_field = DataField.LAB_TEST_NAME_ORDERED
        invalid_filter_field = "invalidFilterField"

        with pytest.raises(ValueError, match=f"Unsupported filter field: {invalid_filter_field}"):
            VectorSearchParams(
                vector=vector,
                data_field=data_field,
                filter_field=invalid_filter_field,
            )

    def test_vector_search_params_with_invalid_filter_value(self):
        """Tests that an invalid filter value raises a validation error in the VectorSearchParams model."""
        vector = [0.1, 0.2, 0.3]
        data_field = "invalid_value"

        with pytest.raises(pydantic.ValidationError):
            VectorSearchParams(
                vector=vector,
                data_field=data_field,
                vector_field="customVectorField",
                filter_field="customFilterField",
                size=5,
                k=3,
            )
