from .eicr import EicrDataField
from .labs import BaseLabField
from .labs import LabTestNameOrdered
from .labs import LabTestNameResulted

EICR_REGISTRY: dict[EicrDataField, type[BaseLabField]] = {
    EicrDataField.LAB_TEST_NAME_RESULTED: LabTestNameResulted,
    EicrDataField.LAB_TEST_NAME_ORDERED: LabTestNameOrdered,
}

_model_name: str = "Snowflake/snowflake-arctic-embed-m"
