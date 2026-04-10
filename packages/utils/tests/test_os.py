import pytest

from utils.os import get_env_var


class TestGetEnvVar:
    def test_get_env_var(self, monkeypatch):
        """Test get_env_var."""
        monkeypatch.setenv("TEST_ENV_VAR", "test_value")
        value = get_env_var("TEST_ENV_VAR")
        assert value == "test_value"

    def test_require_env_not_set(self, monkeypatch):
        """Test get_env_var not set."""
        with pytest.raises(
            OSError,
            match="Missing environment variable: NONEXISTENT_ENV_VAR",
        ):
            get_env_var("NONEXISTENT_ENV_VAR")
