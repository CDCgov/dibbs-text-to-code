from enum import Enum

from configs.lab_interp import LabInterpConfig
from configs.lab_order import LabOrderConfig
from configs.lab_result import LabResultConfig
from configs.lab_value import LabValueConfig

# TODO: using examples provided by APHL - may need to confirm!
_schematron_errors = {
    "lab_order": [
        "Text to Code: Lab Test Name Ordered does not have a @code attribute",
        "Text to Code: Lab Test Name Ordered code and translation data elements @codeSystem attribute are not LOINC 2.16.840.1.113883.6.1",
    ],
    "lab_result": [
        "Text to Code: Lab Test Name Resulted does not have a @code attribute",
        "Text to Code: Lab Test Name Resulted code and translation data elements @codeSystem attribute are not LOINC 2.16.840.1.113883.6.1",
    ],
}


# store all relevant data fields/elements along with their
# configuration class settings
class EicrConfig(Enum):
    lab_order = LabOrderConfig()
    lab_result = LabResultConfig()
    lab_value = LabValueConfig()
    lab_interp = LabInterpConfig()


_model_name: str = "Snowflake/snowflake-arctic-embed-m"
# smaller model to get tests to run faster and with less memory "all-MiniLM-L6-v2" -- size 384
# TOO BIG TO RUN TESTS against ----  "Qwen/Qwen3-Embedding-8B"


def get_configuration_for_data_element(data_field: str):
    """Verifies a specified data field is in focus for the TTC module
    and if it is, will return the class configuration settings for that data field.
    Otherwise, returns None.

    :param data_field: The data field/element, from an eICR, that
        is being evaluated within the TTC module.
    :returns: A configuration setting class for the data field it it is
        within focus, or None, for the TTC module.
    """
    try:
        data_field_config_class = EicrConfig[data_field.strip()].value.__class__
        return data_field_config_class()
    except KeyError:
        return None


def get_data_element_from_schematron_error(schematron_error: str) -> str | None:
    """Given a schematron error message, will return the data field/element
    that the error message is associated with, if any.

    :param schematron_error: The schematron error message being evaluated.
    :returns: The data field/element the schematron error is associated with,
        or None if not found.
    """
    for data_field, error_list in _schematron_errors.items():
        if schematron_error in error_list:
            return data_field
    return None
