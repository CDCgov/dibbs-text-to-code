import typing

import pydantic

from dibbs_text_to_code.schemas import schematron


class BaseLabElement(pydantic.BaseModel):
    """Shared configuration for lab-related TTC processing."""

    data_field: str = pydantic.Field(description="The data field this configuration applies to.")

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

    xpaths: list[schematron.LabXPaths] = pydantic.Field(
        description="Sub-XPath expressions used to extract text."
    )

    schematron_errors: list[schematron.SchematronErrors] = pydantic.Field(
        description="Relevant Schematron error messages."
    )


class LabTestNameResulted(BaseLabElement):
    """The schema a lab test name resulted data field after being extracted from the schematron."""

    data_field: typing.Literal["Lab Test Name Resulted"] = "Lab Test Name Resulted"

    min_word_count: int = 2

    schematron_errors: list[schematron.LabTestNameResultedSchematronErrors]


class LabTestNameOrdered(BaseLabElement):
    """Config for lab test name ordered."""

    data_field: typing.Literal["Lab Test Name Ordered"] = "Lab Test Name Ordered"

    min_word_count: int = 2

    schematron_errors: list[schematron.LabTestNameOrderedSchematronErrors]
