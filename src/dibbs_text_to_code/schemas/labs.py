import pydantic

from dibbs_text_to_code.schemas import eicr
from dibbs_text_to_code.schemas import schematron


class BaseLabField(pydantic.BaseModel):
    """Shared configuration for lab-related TTC processing."""

    data_field: eicr.EicrDataField = pydantic.Field(
        description="The data field this configuration applies to."
    )

    min_word_count: int = pydantic.Field(
        description="Minimum word count required for text to be viable.", ge=0
    )

    @pydantic.field_validator("xpaths", mode="after")
    @classmethod
    def validate_xpaths(cls, v: list[schematron.LabXPaths]) -> list[schematron.LabXPaths]:
        """Validate that at least one Sub-XPath expression is provided."""
        if not v:
            raise ValueError("At least one Sub-XPath expression must be provided.")
        return v

    xpaths: list[str] = pydantic.Field(
        description="Sub-XPath expressions used to extract text.",
        default=list(schematron.LabXPaths),
    )

    schematron_errors: list[schematron.SchematronErrors] = pydantic.Field(
        description="Relevant Schematron error messages.",
        default_factory=list,
    )


class LabTestNameResulted(BaseLabField):
    """The schema a lab test name resulted data field after being extracted from the schematron."""

    data_field: eicr.EicrDataField = eicr.EicrDataField.LAB_TEST_NAME_RESULTED

    min_word_count: int = 2

    schematron_errors: list[schematron.LabTestNameResultedSchematronErrors] = pydantic.Field(
        default_factory=list
    )


class LabTestNameOrdered(BaseLabField):
    """Config for lab test name ordered."""

    data_field: eicr.EicrDataField = eicr.EicrDataField.LAB_TEST_NAME_ORDERED

    min_word_count: int = 2

    schematron_errors: list[schematron.LabTestNameOrderedSchematronErrors] = pydantic.Field(
        default_factory=list
    )
