import pydantic


class LabValueConfig(pydantic.BaseModel):
    """Schema for Lab Value configuration settings."""

    data_field: str = "lab_value"
    """The data field/element this configuration applies to."""

    text_word_count: int = 1
    """The minimum word count required for text to be considered viable for TTC processing."""

    xpaths: list[str] = []
    """The list of Sub XPath expressions to extract text in various locations from the lab value element."""

    schematron_errors: list[str] = []
    """The list of Schematron error messages relevant to the lab value data field."""
