import pytest

from src.augmentation.models.application import ApplicationCode
from src.augmentation.models.config import AugmenterConfig
from src.augmentation.models.config import TTCAugmenterConfig
from src.augmentation.models.document import DocumentType
from src.augmentation.models.eicr import DataField


class TestConfigModel:
    def test_base_config(self):
        """Basic unit test for base (AugmenterConfig) config model."""
        config = AugmenterConfig(
            application_code=ApplicationCode.TEXT_TO_CODE, document_type=DocumentType.EICR, rules={}
        )
        assert config.rules == {}
        assert config.application_code.value == "text-to-code"
        assert config.document_type.value == "eICR Message"

    def test_ttc_config(self):
        """Basic unit test for TTC-specific (TTCAugmenterConfig) config model."""
        config = TTCAugmenterConfig()
        assert config.application_code.value == "text-to-code"
        assert config.document_type.value == "eICR Message"
        assert DataField.LAB_TEST_NAME_RESULTED in config.rules

    def test_ttc_config_with_no_rules(self):
        """Tests raising error when no rules are provided in TTC config."""
        with pytest.raises(
            ValueError, match=r"Configuation rules must contain at least one augmentation rule!"
        ):
            TTCAugmenterConfig(rules={})
