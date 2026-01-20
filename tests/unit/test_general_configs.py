import pytest

from dibbs_text_to_code.configs.general import EicrConfig
from dibbs_text_to_code.configs.general import _model_name
from dibbs_text_to_code.configs.general import _schematron_errors
from dibbs_text_to_code.configs.general import get_configuration_for_data_element
from dibbs_text_to_code.configs.general import get_data_element_from_schematron_error


class TestGeneralConfigs:
    ENUM_CONFIG = EicrConfig
    DATA_FIELDS = ("lab_order", "lab_result", "lab_value", "lab_interp")

    def test_eicr_config_enum(self) -> None:
        assert len(self.ENUM_CONFIG) > 0

        for df in self.ENUM_CONFIG.__members__:
            assert df in self.DATA_FIELDS
            config_class = self.ENUM_CONFIG[df].value
            assert config_class is not None
            assert isinstance(config_class.xpaths, list)

    def test_rules_wrong_data_field(self) -> None:
        with pytest.raises(KeyError):
            _ = self.ENUM_CONFIG["MY_FIELD"].value

    def test_model_name(self) -> None:
        assert _model_name is not None
        assert isinstance(_model_name, str)

    def test_schematron_errors(self) -> None:
        assert len(_schematron_errors) > 0

        for df, errors in _schematron_errors.items():
            assert df in self.DATA_FIELDS
            assert isinstance(errors, list)
            assert len(errors) > 0

    def test_get_data_field_config(self) -> None:
        data_field = "lab_order"
        config = get_configuration_for_data_element(data_field)

        expected_word_count = 2
        expected_num_xpaths = 4

        assert config is not None
        assert hasattr(config, "schematron_errors")
        assert hasattr(config, "text_word_count")
        assert config.text_word_count == expected_word_count
        assert len(config.xpaths) == expected_num_xpaths

    def test_get_data_field_config_wrong_data_element(self) -> None:
        data_field = "MY_field"
        config = get_configuration_for_data_element(data_field)

        assert config is None

    def test_get_data_field_by_schematron_error(self) -> None:
        schematron_error = "Text to Code: Lab Test Name Ordered does not have a @code attribute"
        data_field = get_data_element_from_schematron_error(schematron_error)

        assert data_field == "lab_order"

        schematron_error = "Some unknown error message"
        data_field = get_data_element_from_schematron_error(schematron_error)
        assert data_field is None
