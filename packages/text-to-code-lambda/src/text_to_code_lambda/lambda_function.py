import os
from dataclasses import dataclass
from enum import StrEnum
from io import BytesIO

from aws_lambda_powertools import Logger, Metrics, single_metric
from aws_lambda_powertools.metrics import MetricUnit
from aws_lambda_powertools.utilities.data_classes import SQSEvent, SQSRecord, event_source
from aws_lambda_powertools.utilities.typing import LambdaContext
from opensearchpy import OpenSearch

import lambda_handler
from lambda_handler.models import OpenSearchResult
from shared_models import (
    Code,
    DataField,
    NonstandardCodeInstance,
    PassthroughReason,
    TTCAugmenterInput,
)
from text_to_code.models import Candidate, OpenSearchResultCacheSource
from text_to_code.models.model_info import TTCModelInfo
from text_to_code.models.schematron import SchematronErrorDetail
from text_to_code.services import eicr_processor, evaluator, schematron_processor
from text_to_code.services.embedder import RETRIEVER_MODEL_INFO, embed_batch
from text_to_code.services.reranker import RERANKER_MODEL_INFO, ScoredResult
from text_to_code.services.result_cache import get_cached_results, put_new_cached_result
from text_to_code.services.utils import compute_cache_key

from .matching import Match, match_text
from .models.metadata import Metadata, TTCSchematronIssueDetail

metrics = Metrics()

_METRIC_NAME = "result_cache_value_status"


# Initialize the logger
logger = Logger(service="ttc")
# Environment variables
SCHEMATRON_ERROR_PREFIX = os.getenv("SCHEMATRON_ERROR_PREFIX", "ValidationResponseV2/")
TTC_INPUT_PREFIX = os.getenv("TTC_INPUT_PREFIX", "TextToCodeSubmissionV2/")
TTC_OUTPUT_PREFIX = os.getenv("TTC_OUTPUT_PREFIX", "TTCAugmentationMetadataV2/")
TTC_METADATA_PREFIX = os.getenv("TTC_METADATA_PREFIX", "TTCMetadataV2/")
AWS_REGION = os.getenv("AWS_REGION")
S3_ENDPOINT_URL = os.getenv("S3_ENDPOINT_URL")
OPENSEARCH_ENDPOINT_URL = os.getenv("OPENSEARCH_ENDPOINT_URL")
OPENSEARCH_INDEX = os.getenv("OPENSEARCH_INDEX", "ttc-index")
RESULT_CACHE_INDEX = os.getenv("RESULT_CACHE_INDEX", "ttc-result-cache")

# The retriever/reranker model identifiers recorded in every metadata output
_TTC_MODEL_INFO = TTCModelInfo(
    retriever=RETRIEVER_MODEL_INFO,
    reranker=RERANKER_MODEL_INFO,
)


class HitValue(StrEnum):
    """Enum to represent the value of the hit status of the cache.

    CloudWatch metrics must be numeric, hence the use of `IntEnum`.
    """

    hit = "hit"
    miss = "miss"


@event_source(data_class=SQSEvent)
@logger.inject_lambda_context
def handler(event: SQSEvent, context: LambdaContext) -> dict:
    """Text to Code lambda entry point.

    :param event: The SQS event containing the S3 event data for processing.
    :param context: The Lambda context object.
    :return: A dictionary containing SQS batch item failures.
    """
    opensearch_client = lambda_handler.create_opensearch_client()

    logger.info("Received event", record_count=len(event["Records"]), status="processing")

    return lambda_handler.SqsBatchProcessor(
        process_record=lambda record: process_record(record, opensearch_client),
        is_passthrough=lambda output: output.passthrough_reason is not None,
        completion_message="TTC invocation completed",
        logger=logger,
        on_error=_write_ttc_exception_passthrough_output,
    ).run(event)


def _write_ttc_exception_passthrough_output(record: SQSRecord, error: Exception) -> bool:
    """Write TTC output with passthrough reason of TTC_EXCEPTION when an exception is raised during TTC processing.

    :param record: The SQS record being processed when the exception was raised.
    :param error: The exception that was raised during TTC processing.
    :return: A boolean indicating whether the passthrough output was successfully written to S3.
    """
    if not record.body:
        logger.warning(
            "Unable to write TTC exception passthrough output because SQS body is empty",
            message_id=record.message_id,
            status="skipped",
            passthrough_reason=PassthroughReason.TTC_EXCEPTION,
        )
        return False

    try:
        parsed = lambda_handler.parse_s3_sqs_record(record, TTC_INPUT_PREFIX, logger=logger)

        if parsed is None or not parsed.bucket_name:
            logger.warning(
                "Unable to write TTC exception passthrough output because bucket name is missing",
                message_id=record.message_id,
                status="skipped",
                passthrough_reason=PassthroughReason.TTC_EXCEPTION,
            )
            return False

        persistence_id = parsed.persistence_id
        bucket_name = parsed.bucket_name
        ttc_metadata = Metadata(
            persistence_id=persistence_id,
            passthrough_reason=PassthroughReason.TTC_EXCEPTION,
            error=str(error),
            model_info=_TTC_MODEL_INFO,
        )
        ttc_output = TTCAugmenterInput(
            persistence_id=persistence_id,
            passthrough_reason=PassthroughReason.TTC_EXCEPTION,
        )

        with logger.append_context_keys(
            persistence_id=persistence_id,
            bucket_name=bucket_name,
            trigger_s3_key=parsed.object_key,
        ):
            logger.warning(
                "Writing TTC exception passthrough output",
                status="passthrough",
                passthrough_reason=PassthroughReason.TTC_EXCEPTION,
            )
            _save_outputs(persistence_id, bucket_name, ttc_output, ttc_metadata)

        return True
    except Exception:
        logger.exception(
            "Failed to write TTC exception passthrough output",
            message_id=record.message_id,
            status="error",
            passthrough_reason=PassthroughReason.TTC_EXCEPTION,
        )
        return False


def process_record(record: SQSRecord, opensearch_client: OpenSearch) -> TTCAugmenterInput | None:
    """Process each SQS record.

    :param record: The SQS record to process
    """
    parsed = lambda_handler.parse_s3_sqs_record(record, TTC_INPUT_PREFIX, logger=logger)
    if parsed is None:
        return None

    if not parsed.bucket_name:
        raise ValueError(
            "No bucket name found in S3 event payload. "
            "The TTC lambda derives its target bucket from the event and does not use a "
            "static bucket configuration. Ensure the EventBridge/S3 event includes "
            "detail.bucket.name."
        )

    with logger.append_context_keys(
        persistence_id=parsed.persistence_id,
        bucket_name=parsed.bucket_name,
        trigger_s3_key=parsed.object_key,
    ):
        logger.info("Processing TTC event", status="processing")
        return _process_record_pipeline(
            parsed.persistence_id, opensearch_client, parsed.bucket_name
        )


def _load_schematron_data_fields(persistence_id: str, bucket_name: str) -> list:
    """Load Schematron errors from S3 and extract relevant fields.

    :param persistence_id: The persistence ID extracted from the S3 object key
    :param bucket_name: The S3 bucket name to read from.
    :return: The relevant Schematron data fields for TTC processing.
    """
    object_key = f"{SCHEMATRON_ERROR_PREFIX}{persistence_id}"
    logger.info(
        "Loading Schematron errors",
        bucket_name=bucket_name,
        s3_key=object_key,
        status="processing",
    )
    schematron_errors = lambda_handler.get_file_content_from_s3(
        bucket_name=bucket_name,
        object_key=object_key,
    )

    # Process Schematron errors to identify relevant data fields for TTC processing
    logger.info("Extracting relevant fields", status="processing")
    return schematron_processor.get_data_fields_from_schematron_error(schematron_errors)


def _load_original_eicr(persistence_id: str, bucket_name: str) -> str:
    """Load the original eICR from S3.

    :param persistence_id: The persistence ID extracted from the S3 object key
    :param bucket_name: The S3 bucket name to read from.
    :return: The original eICR content.
    """
    object_key = f"{TTC_INPUT_PREFIX}{persistence_id}"
    logger.info(
        "Retrieving eICR from S3",
        bucket_name=bucket_name,
        s3_key=object_key,
        status="processing",
    )
    original_eicr_content = lambda_handler.get_file_content_from_s3(
        bucket_name=bucket_name, object_key=object_key
    )
    logger.info("Retrieved eICR content", status="success")
    return original_eicr_content


def _save_ttc_metadata_output(
    persistence_id: str,
    metadata_output: Metadata,
    bucket_name: str,
) -> None:
    """Save TTC metadata output to S3.

    :param persistence_id: The persistence ID extracted from the S3 object key
    :param bucket_name: The S3 bucket name to write to.
    :param metadata_output: The metadata model to be saved.
    """
    metadata_key = f"{TTC_METADATA_PREFIX}{persistence_id.removesuffix('.xml')}.json"

    logger.info(
        "Saving TTC metadata output to S3",
        bucket_name=bucket_name,
        s3_key=metadata_key,
        status="processing",
    )
    lambda_handler.put_file(
        file_obj=BytesIO(metadata_output.model_dump_json().encode("utf-8")),
        bucket_name=bucket_name,
        object_key=metadata_key,
    )
    logger.info(
        "Saved TTC metadata output to S3",
        bucket_name=bucket_name,
        s3_key=metadata_key,
        status="success",
    )


def _save_ttc_outputs(
    persistence_id: str,
    ttc_output: TTCAugmenterInput,
    bucket_name: str,
) -> None:
    """Save TTC output and metadata output to S3.

    :param persistence_id: The persistence ID extracted from the S3 object key
    :param ttc_output: The TTC output dictionary.
    :param bucket_name: The S3 bucket name to write to.
    """
    # Save the TTC output to S3 for the Augmentation Lambda to consume
    logger.info(
        "Saving TTC output to S3",
        bucket_name=bucket_name,
        s3_key=f"{TTC_OUTPUT_PREFIX}{persistence_id}",
        status="processing",
    )
    lambda_handler.put_file(
        file_obj=BytesIO(ttc_output.model_dump_json().encode("utf-8")),
        bucket_name=bucket_name,
        object_key=f"{TTC_OUTPUT_PREFIX}{persistence_id}",
    )
    logger.info(
        "Saved TTC output to S3",
        bucket_name=bucket_name,
        s3_key=f"{TTC_OUTPUT_PREFIX}{persistence_id}",
        status="success",
    )


def _record_cache_metric(hit_value: HitValue) -> None:
    """Emit a cache-result metric via CloudWatch EMF."""
    with single_metric(
        name=_METRIC_NAME,
        unit=MetricUnit.Count,
        value=1,
        namespace="ttc-lambda-cache-metrics",
    ) as metric:
        metric.add_dimension(name="cacheResult", value=hit_value.value)
        metric.add_dimension(name="lastLoincUpdate", value="02-23-2026")


@dataclass
class _ErrorWork:
    """Per-schematron-error state threaded through the pipeline's batched phases."""

    error: SchematronErrorDetail
    selected_candidate: Candidate | None
    cache_key: str | None = None
    cached_result: OpenSearchResultCacheSource | None = None
    embedding: list[float] | None = None


# A resolved error: (new_translation, unmatched_message, opensearch_retrieved_scores,
# ranked_results); new_translation is None when no match was made.
type _Resolution = tuple[Code | None, str | None, OpenSearchResult, list[ScoredResult] | None]


def _prepare_error_work(
    schematron_data_fields: list[SchematronErrorDetail],
    processor: eicr_processor.EicrProcessor,
    opensearch_client: OpenSearch,
) -> list[_ErrorWork]:
    """Select a candidate per error and batch-fetch their cache entries and embeddings.

    Phase 1 extracts and selects a candidate per error (CPU only). Phase 2
    checks all candidates against the result cache in one mget before running
    the full embedding, searching, and reranking process. Phase 3 embeds the
    cache-miss candidates in one batched encode call; errors that share a cache
    key share one resolution, so only the first occurrence of each missing key
    is embedded.

    :param schematron_data_fields: The Schematron errors extracted for TTC processing.
    :param processor: The processor wrapping the parsed original eICR.
    :param opensearch_client: The OpenSearch client.
    :return: One work item per error, in the original error order.
    """
    # Phase 1: extract and select a candidate per error (CPU only).
    work_items: list[_ErrorWork] = []
    for error in schematron_data_fields:
        text_candidates = processor.get_text_candidates(error.error_context, error.field)

        logger.info(
            "Evaluating candidates and selecting relevant text for each error in the eICR",
            status="processing",
        )

        selected_candidate = evaluator.select_relevant_text(text_candidates, error.field)
        work = _ErrorWork(error=error, selected_candidate=selected_candidate)
        if selected_candidate:
            work.cache_key = compute_cache_key(selected_candidate.value, error.field)
        work_items.append(work)

    # Phase 2: before we run the full embedding, searching, and reranking
    # process, check all candidates against the result cache in one mget.
    cache_keys = [work.cache_key for work in work_items if work.cache_key is not None]
    if cache_keys:
        cached_results = get_cached_results(opensearch_client, RESULT_CACHE_INDEX, cache_keys)
        for work in work_items:
            if work.cache_key is not None:
                work.cached_result = cached_results.get(work.cache_key)

    # Phase 3: embed the cache-miss candidates in one batched encode call.
    # Errors that share a cache key share one resolution, so only the first
    # occurrence of each missing key is embedded.
    cache_misses: list[_ErrorWork] = []
    miss_texts: list[str] = []
    seen_miss_keys: set[str] = set()
    for work in work_items:
        if work.selected_candidate is None or work.cached_result is not None:
            continue
        if work.cache_key is None or work.cache_key in seen_miss_keys:
            continue
        seen_miss_keys.add(work.cache_key)
        cache_misses.append(work)
        miss_texts.append(work.selected_candidate.value)
    if cache_misses:
        logger.info(
            "Embedding the relevant text strings for each error in the eICR",
            status="processing",
        )
        embeddings = embed_batch(miss_texts)
        for work, vector in zip(cache_misses, embeddings, strict=True):
            work.embedding = vector.tolist()

    return work_items


def _match_candidate(
    selected_candidate: Candidate,
    embedding: list[float],
    data_field: DataField,
    cache_key: str | None,
    opensearch_client: OpenSearch,
) -> _Resolution:
    """Match a cache-miss candidate against OpenSearch and rerank the hits.

    Runs the shared matching step with the candidate's precomputed embedding and
    writes a successful match back to the result cache.

    :param selected_candidate: The candidate selected for the schematron error.
    :param embedding: The candidate's precomputed embedding vector.
    :param data_field: The data field associated with the error.
    :param cache_key: The precomputed result-cache key for the candidate.
    :param opensearch_client: The OpenSearch client.
    :return: The candidate's resolution; ``new_translation`` is None when no
      match was made.
    """
    logger.info(
        "Querying OpenSearch with the relevant text strings and retrieving code suggestions",
        status="processing",
    )
    outcome = match_text(
        selected_candidate.value,
        data_field,
        opensearch_client,
        OPENSEARCH_INDEX,
        embedding=embedding,
    )

    if isinstance(outcome, Match):
        # Make sure we save the results of a successful standardization
        # into the results cache for future use
        put_new_cached_result(
            opensearch_client,
            RESULT_CACHE_INDEX,
            selected_candidate.value,
            data_field,
            outcome.code,
            outcome.top_retriever_score,
            outcome.ranked_results[0]["score"],
            outcome.opensearch_results,
            outcome.ranked_results,
            cache_key=cache_key,
        )
        return outcome.code, None, outcome.opensearch_results, outcome.ranked_results

    return None, outcome.unmatched_reason, outcome.opensearch_results, outcome.ranked_results


def _resolve_error_work(
    work: _ErrorWork,
    resolved_misses: dict[str, _Resolution],
    opensearch_client: OpenSearch,
) -> tuple[Code | None, str | None, OpenSearchResult | None, list[ScoredResult] | None]:
    """Resolve one schematron error to a translation or an unmatched reason.

    Cache hits reuse the cached retrieval artifacts. Cache misses run the
    matching step once per distinct cache key: duplicate candidates reuse the
    first occurrence's resolution (recorded in ``resolved_misses``), mirroring
    the sequential flow where later duplicates hit the cache entry written
    moments earlier — including in the cache metric, which counts a reused
    successful match as a hit.

    :param work: The error's prepared work item (candidate, cache entry, embedding).
    :param resolved_misses: Cache-miss resolutions from earlier errors, keyed by
      cache key; updated in place with this error's resolution on a fresh miss.
    :param opensearch_client: The OpenSearch client.
    :return: The error's resolution; ``new_translation`` is None when no match
      was made.
    """
    selected_candidate = work.selected_candidate

    if selected_candidate is None:
        return None, "No candidate found.", None, None

    # We've got a hit--no need to run our usual processes, we'll
    # just pull out the fields we want to use directly
    if work.cached_result is not None:
        logger.info("Cache hit, retrieving cached results", status="processing")
        _record_cache_metric(HitValue.hit)
        cached_result = work.cached_result
        return (
            cached_result.loinc_code,
            None,
            cached_result.opensearch_retrieved_scores,
            cached_result.reranker_processed_results["results"],
        )

    # Cache miss, so run everything normally, and then finally store
    # the prediction in the cache for future use
    if work.cache_key is None:
        # Unreachable: phase 1 computes a key for every candidate.
        raise ValueError(f"Missing cache key for candidate: {selected_candidate.value}")

    if work.cache_key in resolved_misses:
        resolution = resolved_misses[work.cache_key]
        _record_cache_metric(HitValue.hit if resolution[0] is not None else HitValue.miss)
        return resolution

    _record_cache_metric(HitValue.miss)
    if work.embedding is None:
        # Unreachable: phase 3 embeds every cache-miss candidate.
        raise ValueError(f"Missing embedding for cache-miss candidate: {selected_candidate.value}")

    resolution = _match_candidate(
        selected_candidate,
        work.embedding,
        work.error.field,
        work.cache_key,
        opensearch_client,
    )
    resolved_misses[work.cache_key] = resolution
    return resolution


def _process_record_pipeline(
    persistence_id: str,
    opensearch_client: OpenSearch,
    bucket_name: str,
) -> TTCAugmenterInput:
    """The main pipeline for processing each record.

    The pipeline includes:
    - Retrieving Schematron errors from S3.
    - Extracting relevant data fields from the Schematron errors for TTC processing
    - Retrieving the original eICR from S3
    - Preparing the errors in batched phases — candidate selection, one mget
      cache lookup, one batched embed call (see ``_prepare_error_work``)
    - Resolving each error from the cache or via KNN search + rerank (see
      ``_resolve_error_work``)
    - Creating the output to pass to the Augmentation Lambda and saving it to S3
    - Creating the metadata object to save in S3 for analysis of TTC results

    :param persistence_id: The persistence ID extracted from the S3 object key
    :param opensearch_client: The OpenSearch client.
    :param bucket_name: The S3 bucket name extracted from the triggering event.
    """
    logger.info("Starting TTC processing", status="processing")

    original_eicr_content = _load_original_eicr(persistence_id, bucket_name)
    processor = eicr_processor.EicrProcessor(original_eicr_content)

    schematron_data_fields = _load_schematron_data_fields(persistence_id, bucket_name)
    ttc_schematron_issues_details: list[TTCSchematronIssueDetail] | None = None
    nonstandard_code_replacements: list[NonstandardCodeInstance] = []
    passthrough_reason: PassthroughReason | None = None

    if schematron_data_fields:
        ttc_schematron_issues_details = []
        work_items = _prepare_error_work(schematron_data_fields, processor, opensearch_client)

        # Resolve each error and assemble details in the original error order.
        resolved_misses: dict[str, _Resolution] = {}
        for work in work_items:
            (
                new_translation,
                unmatched_message,
                opensearch_retrieved_scores,
                ranked_results,
            ) = _resolve_error_work(work, resolved_misses, opensearch_client)

            if new_translation is not None:
                nonstandard_code_replacements.append(
                    NonstandardCodeInstance(
                        schematron_error_xpath=work.error.error_context,
                        field_type=work.error.field,
                        new_translation=new_translation,
                    ),
                )

            ttc_schematron_issues_details.append(
                TTCSchematronIssueDetail(
                    candidate=work.selected_candidate,
                    field_type=work.error.field,
                    issue_context=work.error.error_context,
                    issue_id=work.error.error_id,
                    issue_message=work.error.error_message,
                    issue_test=work.error.error_test,
                    unmatched_reason=unmatched_message,
                    new_translation=new_translation,
                    opensearch_retrieved_scores=opensearch_retrieved_scores,
                    reranker_processed_results=ranked_results,
                ),
            )
    else:
        passthrough_reason = PassthroughReason.NO_RELEVANT_SCHEMATRON_ERRORS

    if ttc_schematron_issues_details and all(
        x.unmatched_reason for x in ttc_schematron_issues_details
    ):
        passthrough_reason = PassthroughReason.NO_CODE_MATCHES

    eicr_metadata = processor.eicr_metadata

    ttc_output = TTCAugmenterInput(
        persistence_id=persistence_id,
        original_eicr_id=eicr_metadata.eicr_id,
        nonstandard_codes=nonstandard_code_replacements,
        passthrough_reason=passthrough_reason,
    )
    ttc_metadata = Metadata(
        persistence_id=persistence_id,
        eicr_metadata=eicr_metadata,
        ttc_schematron_issues=ttc_schematron_issues_details,
        passthrough_reason=passthrough_reason,
        model_info=_TTC_MODEL_INFO,
    )

    _save_outputs(persistence_id, bucket_name, ttc_output, ttc_metadata)

    logger.info(
        "TTC processing completed",
        status="matched" if ttc_output.nonstandard_codes else "no_matches_found",
        passthrough_reason=passthrough_reason,
    )

    return ttc_output


def _save_outputs(
    persistence_id: str, bucket_name: str, ttc_output: TTCAugmenterInput, ttc_metadata: Metadata
) -> None:
    """Save TTC output and metadata output to S3.

    :param persistence_id: The persistence ID extracted from the S3 object key
    :param bucket_name: The S3 bucket name to write to.
    :param ttc_output: The TTC output dictionary.
    :param ttc_metadata: The TTC metadata output dictionary.
    """
    _save_ttc_outputs(persistence_id, ttc_output, bucket_name)
    _save_ttc_metadata_output(
        persistence_id,
        ttc_metadata,
        bucket_name,
    )
