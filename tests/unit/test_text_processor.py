from pathlib import Path

from dibbs_text_to_code.services import text_processor

current_dir = Path(__file__).parent


class TestTextProcessor:  # noqa: D101
    def setup_files(self):
        schematron_path = current_dir / "assets" / "test_schematron_errors.xml"
        with open(schematron_path, "r", encoding="utf-8") as f:
            schematron_output = f.read()
            print(len(schematron_output))
        return schematron_output

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

    def test_embed(self):
        input_text = "Influenza virus A and B and SARS-CoV-2 (COVID-19)"
        embedding = text_processor.embed(input_text)

        assert embedding is not None
        assert len(embedding) == 768
        # this is only for the small model - 384
        # this is only for the Qwen model - 4096  # number of dimensions
        assert len(embedding.shape) == 1  # Assuming a 1D tensor for a single string

        input_text = "COVID"

        embedding = text_processor.embed(input_text)

        assert embedding is not None
        assert len(embedding) == 768
        # this is only for the small model - 384
        # this is only for the Qwen model - 4096  # number of dimensions
        assert len(embedding.shape) == 1  # Assuming a 1D tensor for a single string

    def test_get_schematron_error_data_fields(self):
        schematron_errors = self.setup_files()
        result = text_processor.get_data_fields_from_schematron_error(schematron_errors)

        assert result != {}
        assert "lab_result" in result
        assert len(result["lab_result"]) == 2
        assert "lab_order" in result
        assert len(result["lab_order"]) == 1

    def test_get_schematron_error_empty_xml(self):
        schematron_errors = ""
        result = text_processor.get_data_fields_from_schematron_error(schematron_errors)

        assert result == {}
