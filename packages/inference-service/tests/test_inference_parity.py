import numpy as np
import pytest
from test_inference_app import SETTINGS, fake_models

from inference_service.parity import compare

MAX_COSINE_DISTANCE = 0.1
CASES = [
    {"nonstandard_in": "bun", "correct_standardized_code": "Urea nitrogen"},
    {"nonstandard_in": "k+", "correct_standardized_code": "Potassium"},
]


def test_identical_models_agree():
    results = compare(fake_models(SETTINGS), fake_models(SETTINGS), CASES)

    assert results == {
        "max_embedding_cosine_distance": pytest.approx(0, abs=1e-6),
        "rerank_top1_agreement": 1.0,
        "max_rerank_score_delta": 0.0,
    }


class DriftingRetriever:
    def encode(self, sentences: list[str]) -> np.ndarray:
        return np.array([[1.0, 0.0, 0.0]] * len(sentences))


def test_drift_is_reported():
    gpu = fake_models(SETTINGS)
    gpu.retriever = DriftingRetriever()

    results = compare(fake_models(SETTINGS), gpu, CASES)

    assert results["max_embedding_cosine_distance"] > MAX_COSINE_DISTANCE
