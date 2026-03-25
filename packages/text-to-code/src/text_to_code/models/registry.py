from shared_models import DataField

from .labs import BaseLabField
from .labs import LabTestNameOrdered
from .labs import LabTestNameResulted

EICR_REGISTRY: dict[DataField, type[BaseLabField]] = {
    DataField.LAB_TEST_NAME_RESULTED: LabTestNameResulted,
    DataField.LAB_TEST_NAME_ORDERED: LabTestNameOrdered,
}

# Text-to-Code Retrieval model, used for searching approximate neighborhoods
# to find semantically similar candidates
TTC_RETRIEVER: str = "intfloat/e5-large-v2"

# Text-to-Code Reranker model, used for re-scoring and re-sorting the hits
# found by the approximate neighbor search
TTC_RERANKER: str = "cross-encoder/stsb-roberta-large"
