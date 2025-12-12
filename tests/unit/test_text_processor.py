from dibbs_text_to_code.services import text_processor


class TestExtraction:  # noqa: D101
    def test_is_text_viable_wrong_field(self):
        data_field = "LABs"
        text_value = "Here is my test"
        expected_result = False

        assert text_processor.is_text_viable(data_field, text_value) == expected_result

    def test_is_text_viable_empty_txt(self):
        data_field = "lab_order"
        text_value = ""
        expected_result = False

        assert text_processor.is_text_viable(data_field, text_value) == expected_result

        text_value = "    "
        expected_result = False

        assert text_processor.is_text_viable(data_field, text_value) == expected_result

    def test_is_text_viable_lab_order_viable(self):
        data_field = "lab_order"
        text_value = "COVID PCR TEST FROM NASAL SWAB"
        expected_result = True

        assert text_processor.is_text_viable(data_field, text_value) == expected_result

        text_value = "COVID PCR TEST FROM NASAL SWAB"
        expected_result = True

        assert text_processor.is_text_viable(data_field, text_value) == expected_result

    def test_is_text_viable_lab_order_not_viable(self):
        data_field = "lab_order"
        text_value = "COVID PCR"
        expected_result = False

        assert text_processor.is_text_viable(data_field, text_value) == expected_result

        text_value = "COVID"
        expected_result = False

        assert text_processor.is_text_viable(data_field, text_value) == expected_result

    def test_is_text_viable_no_rules_set(self):
        data_field = "lab_value"
        text_value = "COVID PCR TEST"
        expected_result = False

        assert text_processor.is_text_viable(data_field, text_value) == expected_result
