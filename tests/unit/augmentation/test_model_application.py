from augmentation.models import ApplicationCode


class TestApplicationModel:
    def test_applicationcode(self):
        """Smoke tests for ApplicationCode enum."""
        app_enum = ApplicationCode
        assert app_enum.TEXT_TO_CODE.value == "text-to-code"
        assert app_enum.ECR_REFINER.value == "ecr-refinement"
        assert app_enum.QUERY_CONNECTOR.value == "additional-context-data"
