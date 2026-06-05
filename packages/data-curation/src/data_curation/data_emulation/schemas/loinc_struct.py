"""This module contains the schema definition for a LOINC code object
built out of data pulled from the LOINC API, the RELMA Database, and
UMLS. It is used to compile properties for each LOINC code from
separate sources into one object for synthetic data generation.
"""

import enum
from typing import List, Optional

import pydantic


class LabType(str, enum.Enum):
    ORDER = "order"
    OBSERVATION = "observation"
    BOTH = "both"

class LoincStruct(pydantic.BaseModel):
    """
    """
    model_config = pydantic.ConfigDict(from_attributes=True)

    long_common_name: Optional[str] = pydantic.Field(
        default=None,
        description="The Long Common Name of the LOINC code, if it exists."
    )

    short_name: Optional[str] = pydantic.Field(
        default=None,
        description="The Short Name of the LOINC code, if it exists."
    )

    display_name: Optional[str] = pydantic.Field(
        default=None,
        description="The Display Name of the LOINC code, if it exists."
    )

    consumer_name: Optional[str] = pydantic.Field(
        default=None,
        description="The Consumer Name of the LOINC code, if it exists."
    )

    fully_specified_name: Optional[str] = pydantic.Field(
        default=None,
        description="The Fully Specified Name of the LOINC code, if it exists."
    )

    related_names: Optional[List[str]] = pydantic.Field(
        default=None,
        description="The Related Names for this LOINC code, if they exist."
    )

    lab_type: Optional[LabType] = pydantic.Field(
        default=None,
        description="The lab type of this LOINC code, if it exists."
    )

    class_type: Optional[str] = pydantic.Field(
        default=None,
        description=(
            "The laborary class extracted from the 'Basic Attributes' properties "
            "of the LOINC code, if they exist."
        )
    )

    property: Optional[str] = pydantic.Field(
        default=None,
        description="The 'property' component of this LOINC code, if it exists."
    )

    time: Optional[str] = pydantic.Field(
        default=None,
        description="The 'time' component of this LOINC code, if it exists."
    )

    system: Optional[str] = pydantic.Field(
        default=None,
        description="The 'system' component of this LOINC code, if it exists."
    )

    scale: Optional[str] = pydantic.Field(
        default=None,
        description="The 'scale' component of this LOINC code, if it exists."
    )

    method: Optional[str] = pydantic.Field(
        default=None,
        description="The 'method' component of this LOINC code, if it exists."
    )