from src.augmentation.models.application import ApplicationCode


class TestApplicationModel:
    def test_application_code(self):
        """Smoke tests for ApplicationCode enum."""
        app_enum = ApplicationCode
        assert app_enum.TEXT_TO_CODE.value == "text-to-code"
