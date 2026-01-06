from configs.general import MODEL_NAME
from services import evaluator


class TestEvaluator:  # noqa: D101
    def test_set_sentence_transformer(self):
        assert evaluator._model is None

        evaluator._set_sentence_transformer(MODEL_NAME)

        assert isinstance(evaluator._model, evaluator.SentenceTransformer)

    def test_meets_word_count(self):
        text_value = "This is a simple test string"
        word_count = 4
        expected_result = True

        assert evaluator._meets_word_count(text_value, word_count) == expected_result

        word_count = 6
        expected_result = False

        assert evaluator._meets_word_count(text_value, word_count) == expected_result

    def test_is_text_viable_wrong_field(self):
        data_field = "LABs"
        text_value = "Here is my test"
        expected_result = False

        assert evaluator.is_text_viable(data_field, text_value) == expected_result

    def test_is_text_viable_empty_txt(self):
        data_field = "lab_order"
        text_value = ""
        expected_result = False

        assert evaluator.is_text_viable(data_field, text_value) == expected_result

        text_value = "    "
        expected_result = False

        assert evaluator.is_text_viable(data_field, text_value) == expected_result

    def test_is_text_viable_lab_order_viable(self):
        data_field = "lab_order"
        text_value = "COVID PCR TEST FROM NASAL SWAB"
        expected_result = True

        assert evaluator.is_text_viable(data_field, text_value) == expected_result

    def test_is_text_viable_lab_order_not_viable(self):
        data_field = "lab_order"
        text_value = "COVID PCR"
        expected_result = False

        assert evaluator.is_text_viable(data_field, text_value) == expected_result

    def test_is_text_viable_no_rules_set(self):
        data_field = "lab_value"
        text_value = "COVID PCR TEST"
        expected_result = False

        assert evaluator.is_text_viable(data_field, text_value) == expected_result

    def test_embed(self):
        input_text = "Influenza virus A and B and SARS-CoV-2 (COVID-19)"
        embedding = evaluator.embed(input_text)

        assert embedding is not None
        assert len(embedding) == 768
        # this is only for the small model - 384
        # this is only for the Qwen model - 4096  # number of dimensions
        assert len(embedding.shape) == 1  # Assuming a 1D tensor for a single string

        input_text = "COVID"

        embedding = evaluator.embed(input_text)

        assert embedding is not None
        assert len(embedding) == 768
        # this is only for the small model - 384
        # this is only for the Qwen model - 4096  # number of dimensions
        assert len(embedding.shape) == 1  # Assuming a 1D tensor for a single string
