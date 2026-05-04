import random

import pytest

# Shared conftest.py for all packages.


@pytest.fixture(autouse=True)
def fixed_random_seed() -> None:
    """Set random seed for all tests."""
    random.seed(42)


class MockLambdaContext:
    """Mock Lambda context for testing."""

    function_name = "lambda-test-function"
    memory_limit_in_mb = 128
    invoked_function_arn = "arn:aws:lambda:us-east-1:123456789012:function:lambda-test-function"
    aws_request_id = "test-request-id"


@pytest.fixture
def mock_lambda_context() -> MockLambdaContext:
    """Fixture for providing a mock Lambda context."""
    return MockLambdaContext()
