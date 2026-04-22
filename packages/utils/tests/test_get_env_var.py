import pytest

from utils import get_env_variable


class TestGetEnvVariable:
    def test_get_env_variable(self, monkeypatch):
        """Test require env."""
        monkeypatch.setenv("TEST_ENV_VAR", "test_value")
        value = get_env_variable("TEST_ENV_VAR")
        assert value == "test_value"

    def test_require_env_not_set(self, monkeypatch):
        """Test require env not set."""
        nonexistent_env_var = "NONEXISTENT_ENV_VAR"
        with pytest.raises(
            OSError,
            match=f"Missing environment variable: {nonexistent_env_var}",
        ):
            get_env_variable(nonexistent_env_var)
