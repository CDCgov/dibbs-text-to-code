import os
import random

import pytest


@pytest.fixture(autouse=True)
def set_random_seed() -> None:
    """Set a fixed random seed before each test for reproducibility."""
    random.seed(3141)


@pytest.fixture(scope="function")
def cleanup_tmp_files() -> None:
    """Cleanup temporary test files."""
    # Setup: Ensure the tmp directory exists
    os.makedirs("./tmp", exist_ok=True)
    yield
    # Cleanup augmented files after test
    for filename in os.listdir("./tmp"):
        os.remove(os.path.join("./tmp", filename))

    # Optionally, remove the tmp directory if empty
    if not os.listdir("./tmp"):
        os.rmdir("./tmp")
