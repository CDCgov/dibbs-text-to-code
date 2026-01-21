from .eicr import EicrDataField
from .labs import BaseLabField
from .labs import LabTestNameOrdered
from .labs import LabTestNameResulted

EICR_REGISTRY: dict[EicrDataField, type[BaseLabField]] = {
    EicrDataField.LAB_TEST_NAME_RESULTED: LabTestNameResulted,
    EicrDataField.LAB_TEST_NAME_ORDERED: LabTestNameOrdered,
}

# Default model name for SentenceTransformer, representing the model TTC used most extensively
default_model: str = "intfloat/e5-large-v2"
