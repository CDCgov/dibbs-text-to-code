from api import config


class TestConfig:
    data_fields = config.DATA_FIELDS
    data_field_rules = config.DATA_FIELD_TEXT_RULES

    def test_data_fields_and_rules(self):  # noqa: D102, D103
        assert len(self.data_fields) > 0

        for df in self.data_fields:
            df_rules = self.data_field_rules[df]
            assert df_rules is not None
            if df in ("lab_order", "lab_result"):
                assert df_rules["text_length"] is not None and df_rules["text_length"] > 0

    def test_rules_wrong_data_field(self):  # noqa: D102, D103
        assert self.data_field_rules.get("MY FIELD") is None
        assert "MY FIELD" not in self.data_fields
