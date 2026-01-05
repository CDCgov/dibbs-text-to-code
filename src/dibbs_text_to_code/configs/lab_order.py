# Configuration settings for lab ordered processing in the TTC module
import typing

import pydantic


class LabOrderConfig(pydantic.BaseModel):
    """
    Schema for Lab Order configuration settings
    """

    data_field: str = "lab_order"
    """The data field/element this configuration applies to."""

    text_word_count: int = 2
    """The minimum word count required for text to be considered viable for TTC processing."""

    xpaths: typing.List[str] = [
        "/code/@displayName",
        "/code/originalText/text()",
        "/code/text/text()",
        "/code/translation/@displayName",
        "/code/translation/originalText/text()",
        "/code/translation/text/text()",
    ]
    """The list of Sub XPath expressions to extract text in various locations from the lab order element."""

    """
    "/code/@displayName",
    "/cda:code/@displayName",
    "/cda:code/originalText/text()",
    "/cda:code/cda:text/text()",
        "/code/translation/@displayName",
        "/code/translation/originalText/text()",
        "/code/translation/text/text()",
    """

    schematron_errors: typing.List[str] = [
        "Text to Code: Lab Test Name Ordered does not have a @code attribute",
        "Text to Code: Lab Test Name Ordered code and translation data elements @codeSystem attribute are not LOINC 2.16.840.1.113883.6.1",
    ]
    """The list of Schematron error messages relevant to the lab order data field."""
