from services import utils


class TestUtils:  # noqa: D101
    def test_get_data_field_config(self):
        data_field = "lab_order"
        config = utils.get_data_field_config(data_field)

        assert config is not None
        assert hasattr(config, "schematron_errors")
        assert hasattr(config, "text_word_count")
        assert config.text_word_count == 2
        assert len(config.xpaths) == 6

    def test_get_data_field_config_wrong_data_element(self):
        data_field = "MY_field"
        config = utils.get_data_field_config(data_field)

        assert config is None

    def test_get_data_field_by_schematron_error(self):
        schematron_error = "Text to Code: Lab Test Name Ordered does not have a @code attribute"
        data_field = utils.get_data_field_by_schematron_error(schematron_error)

        assert data_field == "lab_order"

        schematron_error = "Some unknown error message"
        data_field = utils.get_data_field_by_schematron_error(schematron_error)
        assert data_field is None
