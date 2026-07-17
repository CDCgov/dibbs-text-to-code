from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from lambda_handler.models import OpenSearchHits, OpenSearchResult, OpenSearchShards
from lambda_handler.models.opensearch import OpenSearchHit, OpenSearchHitSource
from shared_models import LOINC_NAME, LOINC_OID, Code, DataField
from text_to_code_lambda import service


def _hit(loinc_code: str, description: str, loinc_type: str = "Order") -> OpenSearchHit:
    return OpenSearchHit(
        _index="ttc-index",
        _id=loinc_code,
        _score=0.9,
        _source=OpenSearchHitSource(
            id=0,
            loinc_code=loinc_code,
            loinc_name_type="Long Common Name",
            description=description,
            loinc_type=loinc_type,
        ),
    )


def _result(hits: list[OpenSearchHit]) -> OpenSearchResult:
    return OpenSearchResult(
        took=1,
        timed_out=False,
        _shards=OpenSearchShards(total=1, successful=1, skipped=0, failed=0),
        hits=OpenSearchHits(total={"value": len(hits)}, hits=hits),
    )


@pytest.fixture(autouse=True)
def stub_embed(mocker):
    """Avoid running the real retriever model; the embedding value is irrelevant here."""
    mocker.patch.object(
        service, "embed", return_value=SimpleNamespace(tolist=lambda: [0.1, 0.2, 0.3])
    )
    mocker.patch.object(
        service,
        "embed_batch",
        side_effect=lambda texts: [SimpleNamespace(tolist=lambda: [0.1, 0.2, 0.3]) for _ in texts],
    )


def test_code_for_text_returns_top_reranked_code(mocker):
    """The reranker's top result is mapped to a LOINC Code, not OpenSearch's order."""
    hits = [_hit("1111-1", "First candidate"), _hit("2222-2", "Second candidate")]
    mocker.patch.object(
        service.lambda_handler, "retrieve_opensearch_results", return_value=_result(hits)
    )
    # Reranker promotes the second candidate above OpenSearch's first hit.
    mocker.patch.object(
        service,
        "rerank",
        return_value=[
            {"code_string": "Second candidate", "score": 0.9},
            {"code_string": "First candidate", "score": 0.4},
        ],
    )

    code = service.code_for_text("glucose", DataField.LAB_TEST_NAME_ORDERED, MagicMock())

    assert code is not None
    assert code.code == "2222-2"
    assert code.display_name == "Second candidate"
    assert code.code_system == LOINC_OID
    assert code.code_system_name == LOINC_NAME
    assert code.original_text == "glucose"


def test_code_for_text_returns_none_when_no_hits(mocker):
    """No OpenSearch hits short-circuits before reranking."""
    mocker.patch.object(
        service.lambda_handler, "retrieve_opensearch_results", return_value=_result([])
    )
    rerank_mock = mocker.patch.object(service, "rerank")

    code = service.code_for_text("glucose", DataField.LAB_TEST_NAME_ORDERED, MagicMock())

    assert code is None
    rerank_mock.assert_not_called()


def test_code_for_text_returns_none_when_rerank_empty(mocker):
    """An empty reranker result yields no match."""
    mocker.patch.object(
        service.lambda_handler,
        "retrieve_opensearch_results",
        return_value=_result([_hit("1111-1", "Only candidate")]),
    )
    mocker.patch.object(service, "rerank", return_value=[])

    code = service.code_for_text("glucose", DataField.LAB_TEST_NAME_ORDERED, MagicMock())

    assert code is None


def test_results_for_inputs_skips_blank_without_querying(mocker):
    """Blank inputs are returned as unmatched without invoking the pipeline."""
    code_for_text_mock = mocker.patch.object(
        service,
        "code_for_text",
        return_value=Code(
            code="1111-1",
            code_system=LOINC_OID,
            code_system_name=LOINC_NAME,
            display_name="Glucose",
            original_text="glucose",
        ),
    )

    results = service.results_for_inputs(
        ["", "   ", "glucose"], DataField.LAB_TEST_NAME_ORDERED, MagicMock()
    )

    assert [r["matched"] for r in results] == [False, False, True]
    assert results[2]["code"] == "1111-1"
    code_for_text_mock.assert_called_once()


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, DataField.LAB_TEST_NAME_ORDERED),
        ("", DataField.LAB_TEST_NAME_ORDERED),
        ("Lab Test Name Ordered", DataField.LAB_TEST_NAME_ORDERED),
        ("Lab Test Name Resulted", DataField.LAB_TEST_NAME_RESULTED),
        ("not a real field", DataField.LAB_TEST_NAME_ORDERED),
    ],
)
def test_parse_data_field(value, expected):
    assert service.parse_data_field(value) == expected
