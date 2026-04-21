import os
import pathlib
import re
import tempfile
import unittest.mock

import pytest
from utils import path as utils


def test_code_root():
    """Test code root."""
    root = utils.code_root()
    assert root.name == "dibbs-text-to-code"


def test_code_root_not_found():
    """Test code root when not found."""
    with unittest.mock.patch("pathlib.Path.resolve") as mock_resolve:
        mock_resolve.return_value = pathlib.Path("/")
        with pytest.raises(FileNotFoundError):
            utils.code_root()


def test_read_json_relative():
    """Test read JSON with relative path."""
    tmp = utils.code_root() / "test.json"
    with open(tmp, "w") as fobj:
        fobj.write('{"key": "value"}')
    assert utils.read_json("test.json") == {"key": "value"}
    tmp.unlink()


def test_read_json_absolute():
    """Test read JSON with absolute path."""
    fd, path = tempfile.mkstemp(suffix=".json")
    try:
        with os.fdopen(fd, "w") as fobj:
            fobj.write('{"key": "value"}')
        assert utils.read_json(path) == {"key": "value"}
    finally:
        os.unlink(path)


def test_load_loinc_enhancements_raises_when_project_root_missing():
    """Test load LOINC enhancements when project root is missing from cwd."""
    with pytest.raises(
        ValueError,
        match=re.escape("Could not find 'dibbs-text-to-code' in current working directory path."),
    ):
        utils.load_loinc_enhancements("/tmp/not-the-project-root/tests")  # noqa: S108


def test_load_loinc_enhancements():
    """Test load LOINC enhancements CWD."""
    print("test_load_loinc_enhancements cwd", os.getcwd())
    enhancements = utils.load_loinc_enhancements(os.getcwd())
    assert isinstance(enhancements, dict)
    assert len(enhancements) > 0
