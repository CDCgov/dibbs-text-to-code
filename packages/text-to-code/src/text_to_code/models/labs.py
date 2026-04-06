from pydantic import BaseModel
from pydantic import Field
from pydantic import field_validator

from shared_models import DataField
from shared_models import LabXPaths

from .schematron import LabTestNameOrderedSchematronErrors
from .schematron import LabTestNameResultedSchematronErrors
from .schematron import SchematronErrors


class BaseLabField(BaseModel):
    """Shared configuration for lab-related TTC processing."""

    # Made optional at type level for Ty appeasement, defaults filled in subclasses
    data_field: DataField | None = Field(
        default=None, description="The data field this configuration applies to."
    )

    min_word_count: int | None = Field(
        default=None, description="Minimum word count required for text to be viable.", ge=0
    )

    @field_validator("xpaths", mode="after")
    @classmethod
    def validate_xpaths(cls, v: list[LabXPaths]) -> list[LabXPaths]:
        """Validate that at least one Sub-XPath expression is provided."""
        if not v:
            raise ValueError("At least one Sub-XPath expression must be provided.")
        return v

    xpaths: list[LabXPaths] = list(LabXPaths)

    schematron_errors: list[SchematronErrors] = Field(
        description="Relevant Schematron error messages.",
        default_factory=list,
    )


class LabTestNameResulted(BaseLabField):
    """The schema a lab test name resulted data field after being extracted from the schematron."""

    data_field: DataField = DataField.LAB_TEST_NAME_RESULTED

    min_word_count: int = 2

    schematron_errors: list[LabTestNameResultedSchematronErrors] = Field(default_factory=list)


class LabTestNameOrdered(BaseLabField):
    """Config for lab test name ordered."""

    data_field: DataField = DataField.LAB_TEST_NAME_ORDERED

    min_word_count: int = 2

    schematron_errors: list[LabTestNameOrderedSchematronErrors] = Field(default_factory=list)
