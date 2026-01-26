import pytest

from dibbs_text_to_code.services.evaluator import Evaluator
from dibbs_text_to_code.services.evaluator import is_text_viable


class TestEvaluator:
    def test_is_text_viable_wrong_field(self) -> None:
        data_field = "LABs"
        text_value = "Here is my test"
        expected_result = False

        assert is_text_viable(data_field, text_value) == expected_result

    def test_is_text_viable_empty_txt(self) -> None:
        data_field = "lab_order"
        text_value = ""
        expected_result = False

        assert is_text_viable(data_field, text_value) == expected_result

        text_value = "    "
        expected_result = False

        assert is_text_viable(data_field, text_value) == expected_result

    def test_is_text_viable_lab_order_viable(self) -> None:
        data_field = "lab_order"
        text_value = "COVID PCR TEST FROM NASAL SWAB"
        expected_result = True

        assert is_text_viable(data_field, text_value) == expected_result

    def test_is_text_viable_lab_order_not_viable(self) -> None:
        data_field = "lab_order"
        text_value = "COVID PCR"
        expected_result = False

        assert is_text_viable(data_field, text_value) == expected_result

    def test_is_text_viable_no_rules_set(self) -> None:
        data_field = "lab_value"
        text_value = "COVID PCR TEST"
        expected_result = False

        assert is_text_viable(data_field, text_value) == expected_result


class TestEmbedder:
    @pytest.fixture(scope="class")
    def evaluator(self) -> Evaluator:
        return Evaluator()

    @pytest.mark.parametrize(
        ("input_text"), ["Influenza virus A and B and SARS-CoV-2 (COVID-19)", "COVID"]
    )
    def test_embed(self, evaluator: Evaluator, input_text: str) -> None:
        embedding = evaluator.embed(input_text)

        expected_embedding_length = 768

        assert len(embedding) == expected_embedding_length
        # this is only for the small model - 384
        # this is only for the Qwen model - 4096  # number of dimensions
        assert len(embedding.shape) == 1  # Assuming a 1D tensor for a single string
