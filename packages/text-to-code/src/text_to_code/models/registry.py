from shared_models import DataField

from .labs import BaseLabField
from .labs import LabTestNameOrdered
from .labs import LabTestNameResulted

EICR_REGISTRY: dict[DataField, type[BaseLabField]] = {
    DataField.LAB_TEST_NAME_RESULTED: LabTestNameResulted,
    DataField.LAB_TEST_NAME_ORDERED: LabTestNameOrdered,
}

# Default model name for SentenceTransformer, representing the model TTC used most extensively
default_model: str = "intfloat/e5-large-v2"
