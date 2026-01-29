from src.augmentation.models.eicr import ECRDataField


class TestEICRModel:
    def test_ecr_data_field(self):
        """Smoke tests for eicr Data Field enum."""
        ecr_enum = ECRDataField
        assert ecr_enum.LAB_TEST_NAME_RESULTED.value == "Lab Test Name Resulted"
        assert ecr_enum.LAB_TEST_NAME_ORDERED.value == "Lab Test Name Ordered"
