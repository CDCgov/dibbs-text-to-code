from augmentation_lambda import lambda_function
from shared_models import DataField
from shared_models import NonstandardCodeInstance

TTC_OUTPUT_PREFIX = "TTCAugmentationMetadataV2/"


class TestParseNonstandardCodes:
    """Tests for the _parse_nonstandard_codes helper.

    This is testing a private function, which typically do not need to be unit testing, as unit tests should be testing the implementation of the public function, just its output/behaviour.
    """

    def test_parses_valid_ttc_output(self, test_ttc_output) -> None:
        codes = lambda_function._parse_nonstandard_codes(test_ttc_output)

        assert len(codes) == 1
        assert isinstance(codes[0], NonstandardCodeInstance)
        assert codes[0].field_type == DataField.LAB_TEST_NAME_RESULTED
        assert codes[0].new_translation.code == "109224-6"
        assert codes[0].new_translation.code_system == "2.16.840.1.113883.6.1"
        assert codes[0].new_translation.display_name == "Weed Allergen Mix 3 IgE Ab"

    def test_skips_entries_without_new_translation(self) -> None:
        ttc_output = {
            "schematron_errors": {
                "Lab Test Name Resulted": [
                    {
                        "field": "Lab Test Name Resulted",
                        "error": "some error",
                        "error_context": "/some/xpath",
                    }
                ]
            }
        }

        codes = lambda_function._parse_nonstandard_codes(ttc_output)

        assert len(codes) == 0

    def test_handles_empty_schematron_errors(self) -> None:
        codes = lambda_function._parse_nonstandard_codes({"schematron_errors": {}})
        assert len(codes) == 0

    def test_handles_missing_schematron_errors(self) -> None:
        codes = lambda_function._parse_nonstandard_codes({})
        assert len(codes) == 0
