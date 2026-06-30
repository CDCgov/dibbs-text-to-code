from datetime import datetime

import pytest
from huggingface_hub import errors

from shared_models import DataField
from text_to_code.models import LabTestNameResulted
from text_to_code.models.model_info import ModelInfo
from text_to_code.models.registry import TTC_RETRIEVER
from text_to_code.services.utils import get_config_for_data_field, get_model_info


class TestGetConfigForDataField:
    def test_get_config_for_data_field_returns_config_instance(self):
        config = get_config_for_data_field(DataField.LAB_TEST_NAME_RESULTED)

        assert isinstance(config, LabTestNameResulted)
        assert config.data_field == DataField.LAB_TEST_NAME_RESULTED

    def test_get_config_for_data_field_raises_for_unregistered_data_field(self, mocker):
        mocker.patch.dict(
            "text_to_code.services.utils.EICR_REGISTRY",
            {},
            clear=True,
        )

        with pytest.raises(
            KeyError,
            match=r"No config registered for EicrDataField Lab Test Name Resulted",
        ):
            get_config_for_data_field(DataField.LAB_TEST_NAME_RESULTED)


class TestGetModelInfo:
    def test_get_model_info_returns_model_info(self):
        expected_info = ModelInfo(
            id=TTC_RETRIEVER,
            author="NCHS",
            created_at=datetime.fromisoformat("2026-03-30 13:52:42+00:00"),
            last_modified=datetime.fromisoformat("2026-03-30 14:12:37+00:00"),
        )
        info = get_model_info(TTC_RETRIEVER)
        assert info == expected_info

    def test_get_model_info_raises_for_nonexistent_model(self):
        with pytest.raises(Exception, match=r"Model name 'nonexistent-model' was not found"):
            get_model_info("nonexistent-model")

    def test_get_model_info_skips_hub_lookup_for_local_path(self, tmp_path, mocker):
        # Models baked into the container image are referenced by a local path
        # (e.g. /opt/retriever_model), which is not a valid Hub repo id. This must
        # not crash module import by hitting the Hub. Regression test for the prod
        # outage where TTC_RETRIEVER=/opt/retriever_model raised HFValidationError.
        spy = mocker.patch("text_to_code.services.utils.model_info")

        info = get_model_info(str(tmp_path))

        spy.assert_not_called()
        assert info == ModelInfo(
            id=str(tmp_path), author=None, created_at=None, last_modified=None
        )

    def test_get_model_info_degrades_for_invalid_repo_id(self, mocker):
        # A value that is neither a local path nor a valid repo id should degrade
        # to just the id rather than raise and crash startup.
        mocker.patch(
            "text_to_code.services.utils.model_info",
            side_effect=errors.HFValidationError("bad repo id"),
        )

        info = get_model_info("/opt/retriever_model")

        assert info == ModelInfo(
            id="/opt/retriever_model", author=None, created_at=None, last_modified=None
        )
