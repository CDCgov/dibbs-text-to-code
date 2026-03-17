"""
data_curation.schemas.loinc_struct
~~~~~~~~~~~~~~~~~~~~~~~~~

This module contains the schema definition for a LOINC code object
built out of data pulled from the LOINC API, the RELMA Database, and
UMLS. It is used to compile properties for each LOINC code from
separate sources into one object for synthetic data generation.
"""

import enum
import typing

import pydantic


class LabType(str, enum.Enum):
    ORDER = "order"
    OBSERVATION = "observation"
    BOTH = "both"

class LoincStruct(pydantic.BaseModel):
    """
    """
    model_config = pydantic.ConfigDict(from_attributes=True)

    long_common_name: typing.Optional[str] = pydantic.Field(
        default=None,
        description="The Long Common Name of the LOINC code, if it exists."
    )

    short_name: typing.Optional[str] = pydantic.Field(
        default=None,
        description="The Short Name of the LOINC code, if it exists."
    )

    display_name: typing.Optional[str] = pydantic.Field(
        default=None,
        description="The Display Name of the LOINC code, if it exists."
    )

    consumer_name: typing.Optional[str] = pydantic.Field(
        default=None,
        description="The Consumer Name of the LOINC code, if it exists."
    )

    fully_specified_name: typing.Optional[str] = pydantic.Field(
        default=None,
        description="The Fully Specified Name of the LOINC code, if it exists."
    )

    related_names: typing.Optional[typing.List[str]] = pydantic.Field(
        default=None,
        description="The Related Names for this LOINC code, if they exist."
    )

    lab_type: typing.Optional[LabType] = pydantic.Field(
        default=None,
        description="The lab type of this LOINC code, if it exists."
    )

    class_type: typing.Optional[str] = pydantic.Field(
        default=None,
        description=(
            "The laborary class extracted from the 'Basic Attributes' properties "
            "of the LOINC code, if they exist."
        )
    )

    property: typing.Optional[str] = pydantic.Field(
        default=None,
        description="The 'property' component of this LOINC code, if it exists."
    )

    time: typing.Optional[str] = pydantic.Field(
        default=None,
        description="The 'time' component of this LOINC code, if it exists."
    )

    system: typing.Optional[str] = pydantic.Field(
        default=None,
        description="The 'system' component of this LOINC code, if it exists."
    )

    scale: typing.Optional[str] = pydantic.Field(
        default=None,
        description="The 'scale' component of this LOINC code, if it exists."
    )

    method: typing.Optional[str] = pydantic.Field(
        default=None,
        description="The 'method' component of this LOINC code, if it exists."
    )