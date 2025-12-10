from dibbs_text_to_code.configs import DATA_FIELD_TEXT_RULES
from dibbs_text_to_code.configs import DATA_FIELDS


class TestConfigs:
    data_fields = DATA_FIELDS
    data_field_rules = DATA_FIELD_TEXT_RULES

    def test_data_fields_and_rules(self):
        assert len(self.data_fields) > 0

        for df in self.data_fields:
            df_rules = self.data_field_rules[df]
            assert df_rules is not None
            if df in ("lab_order", "lab_result"):
                assert df_rules["text_word_count"] is not None and df_rules["text_word_count"] > 0

    def test_rules_wrong_data_field(self):
        assert self.data_field_rules.get("MY FIELD") is None
        assert "MY FIELD" not in self.data_fields
