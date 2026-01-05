from configs.general import eicr_config
from configs.general import MODEL_NAME
from configs.general import SCHEMATRON_ERRORS


class TestGeneralConfigs:  # noqa: D101
    ENUM_CONFIG = eicr_config
    DATA_FIELDS = ("lab_order", "lab_result", "lab_value", "lab_interp")

    def test_eicr_config_enum(self):
        assert len(self.ENUM_CONFIG) > 0

        for df in self.ENUM_CONFIG.__members__:
            assert df in self.DATA_FIELDS
            config_class = self.ENUM_CONFIG[df].value
            assert config_class is not None
            assert isinstance(config_class.x_paths, list)

    def test_rules_wrong_data_field(self):
        config_class = self.ENUM_CONFIG["MY_FIELD"].value
        assert config_class is None

    def test_model_name(self):
        assert MODEL_NAME is not None
        assert isinstance(MODEL_NAME, str)

    def test_schematron_errors(self):
        assert len(SCHEMATRON_ERRORS) > 0

        for df, errors in SCHEMATRON_ERRORS.items():
            assert df in self
            assert isinstance(errors, list)
            assert len(errors) > 0
