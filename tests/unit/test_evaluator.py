from dibbs_text_to_code.schemas import eicr
from dibbs_text_to_code.schemas import registry
from dibbs_text_to_code.services import evaluator


class TestEvaluator:
    def test_set_sentence_transformer(self) -> None:
        assert evaluator._model is None

        evaluator._set_sentence_transformer(registry._model_name)

        assert isinstance(evaluator._model, evaluator.SentenceTransformer)

    def test_meets_word_count(self) -> None:
        text_value = "This is a simple test string"
        word_count = 4
        expected_result = True

        assert evaluator._meets_word_count(text_value, word_count) == expected_result

        word_count = 6
        expected_result = False

        assert evaluator._meets_word_count(text_value, word_count) == expected_result

    # def test_is_text_viable_wrong_field(self) -> None:
    #     data_field = "LABs"
    #     text_value = "Here is my test"

    #     with pytest.raises(KeyError):
    #         evaluator.is_text_viable(data_field, text_value)

    def test_is_text_viable_empty_txt(self) -> None:
        data_field = eicr.EicrDataField.LAB_TEST_NAME_ORDERED
        text_value = ""
        expected_result = False

        assert evaluator.is_text_viable(data_field, text_value) == expected_result

        text_value = "    "
        expected_result = False

        assert evaluator.is_text_viable(data_field, text_value) == expected_result

    def test_is_text_viable_lab_order_viable(self) -> None:
        data_field = eicr.EicrDataField.LAB_TEST_NAME_ORDERED
        text_value = "COVID PCR TEST FROM NASAL SWAB"
        expected_result = True

        assert evaluator.is_text_viable(data_field, text_value) == expected_result

    def test_is_text_viable_lab_order_not_viable(self) -> None:
        data_field = eicr.EicrDataField.LAB_TEST_NAME_ORDERED
        text_value = "COVID PCR"
        expected_result = False

        assert evaluator.is_text_viable(data_field, text_value) == expected_result

    def test_embed(self) -> None:
        input_text = "Influenza virus A and B and SARS-CoV-2 (COVID-19)"
        embedding = evaluator.embed(input_text)

        expected_embedding_length = 768

        assert embedding is not None
        assert len(embedding) == expected_embedding_length
        # this is only for the small model - 384
        # this is only for the Qwen model - 4096  # number of dimensions
        assert len(embedding.shape) == 1  # Assuming a 1D tensor for a single string

        input_text = "COVID"

        embedding = evaluator.embed(input_text)

        expected_embedding_length = 768

        assert embedding is not None
        assert len(embedding) == expected_embedding_length
        # this is only for the small model - 384
        # this is only for the Qwen model - 4096  # number of dimensions
        assert len(embedding.shape) == 1  # Assuming a 1D tensor for a single string
