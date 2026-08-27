import os

from shared_models import DataField

from .labs import BaseLabField, LabTestNameOrdered, LabTestNameResulted

EICR_REGISTRY: dict[DataField, type[BaseLabField]] = {
    DataField.LAB_TEST_NAME_RESULTED: LabTestNameResulted,
    DataField.LAB_TEST_NAME_ORDERED: LabTestNameOrdered,
}

# Text-to-Code Retrieval model, used for searching approximate neighborhoods
# to find semantically similar candidates
RETRIEVER_MODEL_VERSION: str = os.getenv("RETRIEVER_MODEL_VERSION") or "1.0"
TTC_RETRIEVER: str = (
    os.getenv("RETRIEVER_MODEL_PATH") or f"NCHS/ttc-retriever-v{RETRIEVER_MODEL_VERSION}"
)

# Text-to-Code Reranker model, used for re-scoring and re-sorting the hits
# found by the approximate neighbor search
RERANKER_MODEL_VERSION: str = os.getenv("RERANKER_MODEL_VERSION") or "1.0"
TTC_RERANKER: str = (
    os.getenv("RERANKER_MODEL_PATH") or f"NCHS/ttc-reranker-v{RERANKER_MODEL_VERSION}"
)


# The threshold for automatically accepting a top retriever result without sending to the reranker.
AUTO_ACCEPT_THRESHOLD: float = float(os.getenv("AUTO_ACCEPT_THRESHOLD") or 0.95)

# The threshold of combined cosine similarity plus margin above the next-best score, beyond
# which we will automatically accept the retriever's leading candidate.
LEADER_MARGIN: float = float(os.getenv("LEADER_MARGIN") or 1.005)

# The threshold which, if a sufficient number of retriever candidates exceed in scoring, we
# will perform a pre-thresholded re-ranking consisting of all candidates with scores above
# this value and bypassing adaptive margin pruning.
HIGH_RANK_THRESHOLD: float = float(os.getenv("HIGH_RANK_THRESHOLD") or 0.92)
# The number of OpenSearch candidates whose scores must exceed the high rank threshold in order
# to perform pre-thresholded reranking.
MINIMUM_HITS_TO_HIGH_RANK: int = int(os.getenv("MINIMUM_HITS_TO_HIGH_RANK") or 2)

# These numbers were determined empirically by testing the 650k production results from
# APHL and measuring the distribution of scores. The mininum and maxmium margins represent
# the 10th and 95th percentiles of the distribution of margins.
# The minimum margin for determining how many candidates are within a margin of the top score.
MIN_MARGIN: float = float(os.getenv("MIN_MARGIN") or 0.01)
# The maximum margin for determining how many candidates are within a margin of the top score.
MAX_MARGIN: float = float(os.getenv("MAX_MARGIN") or 0.1)
# The low score for interpolating the margin..
LOW_SCORE: float = float(os.getenv("LOW_SCORE") or 0.7)
# The high score for interpolating the margin.
HIGH_SCORE: float = float(os.getenv("HIGH_SCORE") or 0.95)
