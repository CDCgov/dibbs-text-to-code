from pathlib import Path

from dibbs_text_to_code.services import text_processor

current_dir = Path(__file__).parent


class TestTextProcessor:  # noqa: D101
    def get_schematron_output_file(self):
        schematron_path = current_dir / "assets" / "test_schematron_errors.xml"
        with open(schematron_path, "r", encoding="utf-8") as f:
            schematron_output = f.read()
        return schematron_output

    def get_test_eicr_file(self):
        eicr_path = current_dir / "assets" / "test_eicr_covid.xml"
        with open(eicr_path, "r", encoding="utf-8") as f:
            eicr_output = f.read()
        return eicr_output

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
        schematron_errors = self.get_schematron_output_file()
        eicr_xml = self.get_test_eicr_file()
        error_result = text_processor.get_data_fields_from_schematron_error(schematron_errors)

        assert error_result != {}
        assert "lab_result" in error_result
        assert len(error_result["lab_result"]) == 2
        assert "lab_order" in error_result
        assert len(error_result["lab_order"]) == 1

        xpaths = error_result["lab_result"][1]
        result = text_processor.get_text_candidates(eicr_xml, xpaths, "lab_result")
        assert len(result) == 7
        assert (
            result[0]
            == "SARS-like Coronavirus N gene [Presence] in Unspecified specimen by NAA with probe detection"
        )
        assert result[6] == "SARS-like Virus"

    def test_get_schematron_error_empty_xml(self):
        schematron_errors = ""
        result = text_processor.get_data_fields_from_schematron_error(schematron_errors)

        assert result == {}

    def test_get_schematron_error_data_fields_empty(self):
        schematron_errors = self.get_schematron_output_file()
        result = text_processor.get_data_fields_from_schematron_error(schematron_errors)

        xpath = result["lab_result"][1]
        result = text_processor.get_text_candidates("", xpath, "lab_result")
        assert len(result) == 0
