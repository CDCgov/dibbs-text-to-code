import pytest

from dibbs_text_to_code.models import BaseLabField
from dibbs_text_to_code.models import LabTestNameOrdered
from dibbs_text_to_code.models import LabTestNameOrderedSchematronErrors
from dibbs_text_to_code.models import LabTestNameResulted
from dibbs_text_to_code.models import LabTestNameResultedSchematronErrors
from dibbs_text_to_code.models import LabXPaths


class TestLabSchemas:
    def test_base_lab_element_requires_xpaths(self):
        """Tests raising error when no xpaths are provided."""
        with pytest.raises(
            ValueError, match=r"At least one Sub-XPath expression must be provided."
        ):
            BaseLabField(
                data_field="Lab Test Name Resulted",
                min_word_count=2,
                xpaths=[],
                schematron_errors=[],
            )

    def test_lab_test_name_resulted_defaults(self):
        """Tests default values for LabTestNameResulted schema."""
        lab_test = LabTestNameResulted(
            schematron_errors=LabTestNameResultedSchematronErrors,
        )
        assert lab_test.data_field == "Lab Test Name Resulted"
        assert lab_test.min_word_count == LabTestNameResulted.model_fields["min_word_count"].default
        assert lab_test.xpaths == list(LabXPaths)
        assert lab_test.schematron_errors == list(LabTestNameResultedSchematronErrors)

    def test_lab_test_name_ordered_defaults(self):
        """Tests default values for LabTestNameOrdered schema."""
        lab_test = LabTestNameOrdered(
            schematron_errors=LabTestNameOrderedSchematronErrors,
        )
        assert lab_test.data_field == "Lab Test Name Ordered"
        assert lab_test.min_word_count == LabTestNameOrdered.model_fields["min_word_count"].default
        assert lab_test.xpaths == list(LabXPaths)
        assert lab_test.schematron_errors == list(LabTestNameOrderedSchematronErrors)

    def test_lab_test_name_resulted_custom_xpaths(self):
        """Tests setting custom xpaths for LabTestNameResulted schema."""
        custom_xpaths = ["/custom/xpath1", "/custom/xpath2"]
        lab_test = LabTestNameResulted(
            xpaths=custom_xpaths,
            schematron_errors=LabTestNameResultedSchematronErrors,
        )
        assert lab_test.xpaths == custom_xpaths
