from datetime import UTC, datetime

from pydantic import Field

from lambda_handler.models import OpenSearchResult
from shared_models import Code, DataField, FrozenBaseModel, PassthroughReason
from text_to_code.models.eicr import Candidate
from text_to_code.models.eicr import Metadata as EICRMetadata
from text_to_code.models.model_info import TTCModelInfo
from text_to_code.services.reranker import ScoredResult


class TTCSchematronIssueDetail(FrozenBaseModel):
    """The data describing the TTC response to a relevant Schematron issue.

    This is part of the TTC metadata.
    """

    candidate: Candidate | None
    field_type: DataField
    issue_context: str
    issue_id: str | None
    issue_message: str
    issue_test: str | None
    new_translation: Code | None
    opensearch_retrieved_scores: OpenSearchResult | None
    reranker_processed_results: list[ScoredResult] | None
    unmatched_reason: str | None
    auto_mapped: bool = False


class Metadata(FrozenBaseModel):
    """Model to hold metadata about the TTC process."""

    persistence_id: str
    eicr_metadata: EICRMetadata | None = None
    ttc_schematron_issues: list[TTCSchematronIssueDetail] | None = None
    processed_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    passthrough_reason: PassthroughReason | None = None
    error: str | None = None
    model_info: TTCModelInfo | None = None
