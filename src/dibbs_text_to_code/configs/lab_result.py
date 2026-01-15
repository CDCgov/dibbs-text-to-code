import pydantic


class LabResultConfig(pydantic.BaseModel):
    """Schema for Lab Resulting configuration settings."""

    data_field: str = "lab_result"
    """The data field/element this configuration applies to."""

    text_word_count: int = 2
    """The minimum word count required for text to be considered viable for TTC processing."""

    xpaths: list[str] = [
        "/code/@displayName",
        "/code/originalText",
        "/code/text",
        "/code/translation/@displayName",
        "/code/translation/originalText",
        "/code/translation/text",
    ]
    """The list of Sub XPath expressions to extract text in various locations from the lab result element."""

    schematron_errors: list[str] = [
        "Text to Code: Lab Test Name Resulted does not have a @code attribute",
        "Text to Code: Lab Test Name Resulted code and translation data elements @codeSystem attribute are not LOINC 2.16.840.1.113883.6.1",
    ]
    """The list of Schematron error messages relevant to the lab result data field."""
