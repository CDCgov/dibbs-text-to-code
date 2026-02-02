import pytest

from src.augmentation.models.application import ApplicationCode
from src.augmentation.models.config import AugmentorConfig
from src.augmentation.models.config import TTCAugmentorConfig
from src.augmentation.models.document import DocumentType


class TestConfigModel:
    def test_base_config(self):
        """Smoke tests for base (AugmentorConfig) config model."""
        config = AugmentorConfig(
            application_code=ApplicationCode.TEXT_TO_CODE, document_type=DocumentType.EICR, rules={}
        )
        assert config.rules == {}
        assert config.application_code.value == "text-to-code"
        assert config.document_type.value == "eICR Message"

    def test_ttc_config(self):
        """Smoke tests for TTC-specific (TTCAugmentorConfig) config model."""
        config = TTCAugmentorConfig()
        assert config.application_code.value == "text-to-code"
        assert config.document_type.value == "eICR Message"
        assert "lab_test_name_resulted" in config.rules

    def test_ttc_config_with_no_rules(self):
        """Tests raising error when no rules are provided in TTC config."""
        with pytest.raises(
            ValueError, match=r"Configuation rules must contain at least one augmentation rule!"
        ):
            TTCAugmentorConfig(rules={})
