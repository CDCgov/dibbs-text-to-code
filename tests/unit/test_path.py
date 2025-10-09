import os
import pathlib
import tempfile
import unittest.mock

import pytest

from utils import path as utils


def test_code_root():
    root = utils.code_root()
    assert root.name == "dibbs-text-to-code"


def test_code_root_not_found():
    with unittest.mock.patch("pathlib.Path.resolve") as mock_resolve:
        mock_resolve.return_value = pathlib.Path("/")
        with pytest.raises(FileNotFoundError):
            utils.code_root()


def test_repo_root():
    root = utils.repo_root()
    assert root is not None


def test_repo_root_not_found():
    with unittest.mock.patch("pathlib.Path.resolve") as mock_resolve:
        mock_resolve.return_value = pathlib.Path("/")
        root = utils.repo_root()
        assert root is None


def test_read_json_relative():
    tmp = utils.code_root() / "test.json"
    with open(tmp, "w") as fobj:
        fobj.write('{"key": "value"}')
    assert utils.read_json("test.json") == {"key": "value"}
    tmp.unlink()


def test_read_json_absolute():
    fd, path = tempfile.mkstemp(suffix=".json")
    try:
        with os.fdopen(fd, "w") as fobj:
            fobj.write('{"key": "value"}')
        assert utils.read_json(path) == {"key": "value"}
    finally:
        os.unlink(path)


def test_load_loinc_enhancements():
    enhancements = utils.load_loinc_enhancements(os.getcwd())
    assert isinstance(enhancements, dict)
    assert len(enhancements) > 0
