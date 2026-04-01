import pytest

from shared_models import DataField
from text_to_code.models import LabTestNameResulted
from text_to_code.services.utils import get_config_for_data_field


class TestUtils:
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
