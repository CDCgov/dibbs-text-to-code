"""
dibbs_text_to_code.schemas.augmentaion
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

This module contains the schema definitions for augmentaion.
"""

import typing

import pydantic


class LoincEnhancements(pydantic.BaseModel):
    """
    A schema for LOINC enhancements.
    """

    abbreviations: typing.List[str]
    acronyms: typing.List[str]
    replacement: typing.List[str]
