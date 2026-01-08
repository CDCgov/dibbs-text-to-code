import random

import pytest

# Shared conftest.py for all packages.


@pytest.fixture(autouse=True)
def fixed_random_seed() -> None:
    """Set random seed for all tests."""
    random.seed(42)
