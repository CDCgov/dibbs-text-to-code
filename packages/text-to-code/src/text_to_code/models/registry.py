import os

from shared_models import DataField

from .labs import BaseLabField, LabTestNameOrdered, LabTestNameResulted

EICR_REGISTRY: dict[DataField, type[BaseLabField]] = {
    DataField.LAB_TEST_NAME_RESULTED: LabTestNameResulted,
    DataField.LAB_TEST_NAME_ORDERED: LabTestNameOrdered,
}

# Text-to-Code Retrieval model, used for searching approximate neighborhoods
# to find semantically similar candidates
TTC_RETRIEVER: str = os.getenv("RETRIEVER_MODEL_PATH") or "NCHS/ttc-retriever-mvp"

# Text-to-Code Reranker model, used for re-scoring and re-sorting the hits
# found by the approximate neighbor search
TTC_RERANKER: str = os.getenv("RERANKER_MODEL_PATH") or "NCHS/ttc-reranker-mvp"
