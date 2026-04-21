

class TestGetEnvVariable:
    def test_get_env_variable(self, monkeypatch):
        """Test require env."""
        monkeypatch.setenv("TEST_ENV_VAR", "test_value")
        value = lambda_handler.require_env("TEST_ENV_VAR")
        assert value == "test_value"

    def test_require_env_not_set(self, monkeypatch):
        """Test require env not set."""
        with pytest.raises(
            ValueError,
            match=r"NONEXISTENT_ENV_VAR not set as an environment variable\.",
        ):
            lambda_handler.require_env("NONEXISTENT_ENV_VAR")