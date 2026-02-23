from shared_models import DataField


class TestEICRModel:
    def test_datafield_enum(self):
        """Basic unit test for base (AugmenterConfig) config model."""
        expected_size = 2
        assert DataField.LAB_TEST_NAME_RESULTED.value == "Lab Test Name Resulted"
        assert len(DataField) == expected_size
