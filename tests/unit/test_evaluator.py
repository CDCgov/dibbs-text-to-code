import pytest

from dibbs_text_to_code.models.eicr import DataField
from dibbs_text_to_code.services.evaluator import is_text_viable


class TestEvaluator:
    def test_is_text_viable_wrong_field(self):
        data_field = "LABs"
        text_value = "Here is my test"

        with pytest.raises(KeyError):
            is_text_viable(data_field, text_value)

    def test_is_text_viable_empty_txt(self):
        data_field = DataField.LAB_TEST_NAME_ORDERED
        text_value = ""
        expected_result = False

        assert is_text_viable(data_field, text_value) == expected_result

        text_value = "    "
        expected_result = False

        assert is_text_viable(data_field, text_value) == expected_result

    def test_is_text_viable_lab_order_viable(self):
        data_field = DataField.LAB_TEST_NAME_ORDERED
        text_value = "COVID PCR TEST FROM NASAL SWAB"
        expected_result = True

        assert is_text_viable(data_field, text_value) == expected_result

    def test_is_text_viable_lab_order_not_viable(self):
        data_field = DataField.LAB_TEST_NAME_ORDERED
        text_value = "COVID PCR"
        expected_result = False

        assert is_text_viable(data_field, text_value) == expected_result
