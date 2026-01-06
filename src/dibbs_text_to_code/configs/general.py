from enum import Enum

from configs.lab_interp import LabInterpConfig
from configs.lab_order import LabOrderConfig
from configs.lab_result import LabResultConfig
from configs.lab_value import LabValueConfig


# store all relevant data fields/elements along with their
# configuration class settings
class EicrConfig(Enum):
    lab_order = LabOrderConfig()
    lab_result = LabResultConfig()
    lab_value = LabValueConfig()
    lab_interp = LabInterpConfig()


MODEL_NAME = "Snowflake/snowflake-arctic-embed-m"
# smaller model to get tests to run faster and with less memory "all-MiniLM-L6-v2" -- size 384
# TOO BIG TO RUN TESTS against ----  "Qwen/Qwen3-Embedding-8B"


# TODO: using examples provided by APHL - may need to confirm!
SCHEMATRON_ERRORS = {
    "lab_order": [
        "Text to Code: Lab Test Name Ordered does not have a @code attribute",
        "Text to Code: Lab Test Name Ordered code and translation data elements @codeSystem attribute are not LOINC 2.16.840.1.113883.6.1",
    ],
    "lab_result": [
        "Text to Code: Lab Test Name Resulted does not have a @code attribute",
        "Text to Code: Lab Test Name Resulted code and translation data elements @codeSystem attribute are not LOINC 2.16.840.1.113883.6.1",
    ],
}
