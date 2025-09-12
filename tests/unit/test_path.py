import pathlib
import unittest.mock

import pytest

from dibbs_text_to_code import main as main
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


# def test_rel_path():
#     assert main.rel_path(main.code_root()).endswith("src/dibbs_text_to_code")


def test_read_json_relative():
    tmp = utils.code_root() / "test.json"
    with open(tmp, "w") as fobj:
        fobj.write('{"key": "value"}')
    assert utils.read_json("test.json") == {"key": "value"}
    tmp.unlink()


# def test_read_json_absolute():
#     tmp = tempfile.NamedTemporaryFile(suffix=".json")
#     with open(tmp.name, "w") as fobj:
#         fobj.write('{"key": "value"}')
#     assert utils.read_json(tmp.name) == {"key": "value"}
#     tmp.close()
