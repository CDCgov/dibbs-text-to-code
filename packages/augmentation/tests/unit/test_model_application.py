from augmentation.models.application import ApplicationCode


class TestApplicationModel:
    def test_application_code(self):
        """Basic unit test for ApplicationCode enum."""
        app_enum = ApplicationCode
        assert app_enum.TEXT_TO_CODE.value == "text-to-code"
