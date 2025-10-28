import pytest
import os

@pytest.fixture(scope="function")
def cleanup_tmp_files():
    # Setup: Ensure the tmp directory exists
    os.makedirs("./tmp", exist_ok=True)
    yield
    # Cleanup augmented files after test
    for filename in os.listdir("./tmp"):
        os.remove(os.path.join("./tmp", filename))

    # Optionally, remove the tmp directory if empty
    if not os.listdir("./tmp"):
        os.rmdir("./tmp")