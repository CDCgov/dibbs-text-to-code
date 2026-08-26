import json
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
    LOINC_NAME,
    LOINC_OID,
    Code,
    DataField,
    NonstandardCodeInstance,
    PassthroughReason,
    TTCAugmenterInput,
)
from text_to_code.models import Candidate, OpenSearchResultCacheSource
from text_to_code.models import query as query_models
from text_to_code.models.model_info import TTCModelInfo
from text_to_code.models.schematron import SchematronErrorDetail
from text_to_code.services import eicr_processor, evaluator, schematron_processor
from text_to_code.services.embedder import RETRIEVER_MODEL_INFO, embed_batch
from text_to_code.services.query import QueryBuilder
from text_to_code.services.reranker import RERANKER_MODEL_INFO, ScoredResult, rerank
from text_to_code.services.result_cache import get_cached_results, put_new_cached_result
from text_to_code.services.utils import compute_cache_key

from .models.metadata import Metadata, TTCSchematronIssueDetail

metrics = Metrics()

_METRIC_NAME = "result_cache_value_status"

# Parameters governing the behavior of search-score heuristics, such as
# auto-acceptance or "high-threshold" ranking.
HIGH_RANK_THRESHOLD = 0.92
MINIMUM_HITS_TO_HIGH_RANK = 2
LEADER_MARGIN = 1.005


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

    if any(record.body for record in event.records):
        _validate_opensearch_index(opensearch_client)

    batch_item_failures: list[dict[str, str]] = []
    failures: list[dict[str, object]] = []
    successes: list[dict[str, str]] = []

    for record in event.records:
        try:
            output = process_record(record, opensearch_client)

            if output is None:
                successes.append(
                    {
                        "message_id": record.message_id,
                        "status": "skipped",
                    }
                )
            elif output.passthrough_reason is not None:
                successes.append(
                    {
                        "message_id": record.message_id,
                        "status": "passthrough_written",
                    }
                )
            else:
                successes.append(
                    {
                        "message_id": record.message_id,
                        "status": "processed",
                    }
                )
        except Exception as e:
            logger.exception(
                "Error processing record",
                error=str(e),
                message_id=record.message_id,
                status="error",
            )
            passthrough_written = _write_ttc_exception_passthrough_output(record, e)
            failures.append(
                {
                    "error": str(e),
                    "error_type": type(e).__name__,
                    "message_id": record.message_id,
                    "passthrough_written": passthrough_written,
                    "sqs_retry": not passthrough_written,
                }
            )

            if passthrough_written:
                successes.append(
                    {
                        "message_id": record.message_id,
                        "status": "passthrough_written",
                    }
                )
            else:
                batch_item_failures.append({"itemIdentifier": record.message_id})

    if batch_item_failures:
        status = "partial_failure"
    elif any(success["status"] == "passthrough_written" for success in successes):
        status = "success_with_passthrough"
    else:
        status = "success"

    response: dict[str, object] = {
        "batchItemFailures": batch_item_failures,
        "failures": failures,
        "message": "TTC invocation completed",
        "num_failure_eicrs": len(batch_item_failures),
        "num_processing_error_eicrs": len(failures),
        "num_success_eicrs": len(successes),
        "status": status,
        "successes": successes,
    }

    logger.info(
        "TTC invocation completed",
        batch_item_failures=batch_item_failures,
        failures=failures,
        num_failure_eicrs=len(batch_item_failures),
        num_processing_error_eicrs=len(failures),
        num_success_eicrs=len(successes),
        status=status,
        successes=successes,
    )

    return response


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
        s3_event = json.loads(record.body)
        eventbridge_data = lambda_handler.get_eventbridge_data_from_s3_event(s3_event)
        object_key = eventbridge_data["object_key"]
        bucket_name = eventbridge_data.get("bucket_name")

        if not bucket_name:
            logger.warning(
                "Unable to write TTC exception passthrough output because bucket name is missing",
                message_id=record.message_id,
                status="skipped",
                passthrough_reason=PassthroughReason.TTC_EXCEPTION,
            )
            return False

        persistence_id = lambda_handler.get_persistence_id(object_key, TTC_INPUT_PREFIX)
        ttc_metadata = Metadata(
            persistence_id=persistence_id,
            passthrough_reason=PassthroughReason.TTC_EXCEPTION,
            error=str(error),
            model_info=TTCModelInfo(
                reranker=RERANKER_MODEL_INFO,
                retriever=RETRIEVER_MODEL_INFO,
            ),
        )
        ttc_output = TTCAugmenterInput(
            persistence_id=persistence_id,
            passthrough_reason=PassthroughReason.TTC_EXCEPTION,
        )

        with logger.append_context_keys(
            persistence_id=persistence_id,
            bucket_name=bucket_name,
            trigger_s3_key=object_key,
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
    if not record.body:
        logger.warning("Empty SQS body", message_id=record.message_id, status="skipped")
        return None

    s3_event = json.loads(record.body)

    # Parse the EventBridge S3 event from the SQS message body
    eventbridge_data = lambda_handler.get_eventbridge_data_from_s3_event(s3_event)
    object_key = eventbridge_data["object_key"]
    bucket_name = eventbridge_data.get("bucket_name")

    if not bucket_name:
        raise ValueError(
            "No bucket name found in S3 event payload. "
            "The TTC lambda derives its target bucket from the event and does not use a "
            "static bucket configuration. Ensure the EventBridge/S3 event includes "
            "detail.bucket.name."
        )

    # Extract persistence_id from the RR object key
    persistence_id = lambda_handler.get_persistence_id(object_key, TTC_INPUT_PREFIX)

    with logger.append_context_keys(
        persistence_id=persistence_id,
        bucket_name=bucket_name,
        trigger_s3_key=object_key,
    ):
        logger.info("Processing TTC event", status="processing")
        return _process_record_pipeline(persistence_id, opensearch_client, bucket_name)


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
    :param s3_client: The S3 client to use for fetching files.
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
    :param ttc_metadata_output: The TTC metadata output dictionary.
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


@dataclass
class _CandidateResolution:
    """Resolved TTC result for one selected candidate."""

    new_translation: Code | None = None
    unmatched_message: str | None = None
    opensearch_retrieved_scores: OpenSearchResult | None = None
    ranked_results: list[ScoredResult] | None = None


def _match_candidate(
    selected_candidate: Candidate,
    embedding: list[float],
    data_field: DataField,
    cache_key: str | None,
    opensearch_client: OpenSearch,
) -> tuple[Code | None, str | None, OpenSearchResult, list[ScoredResult] | None]:
    """Match a cache-miss candidate against OpenSearch and rerank the hits.

    Runs the KNN query with the candidate's precomputed embedding, reranks the
    hits, and writes a successful match back to the result cache.

    :param selected_candidate: The candidate selected for the schematron error.
    :param embedding: The candidate's precomputed embedding vector.
    :param data_field: The data field associated with the error.
    :param cache_key: The precomputed result-cache key for the candidate.
    :param opensearch_client: The OpenSearch client.
    :return: A ``(new_translation, unmatched_message, opensearch_retrieved_scores,
      ranked_results)`` tuple; ``new_translation`` is None when no match was made.
    """
    new_translation = None
    unmatched_message = None
    ranked_results: list[ScoredResult] | None = None

    vector_parameters = query_models.VectorSearchParams(vector=embedding, data_field=data_field)

    logger.info(
        "Querying OpenSearch with the relevant text strings and retrieving code suggestions",
        status="processing",
    )
    query = QueryBuilder().with_vector_search(vector_parameters).build()

    opensearch_retrieved_scores = lambda_handler.retrieve_opensearch_results(
        query=query, index=OPENSEARCH_INDEX, opensearch_client=opensearch_client
    )

    # The OpenSearch results object has a couple levels of nesting,
    # but all we care about for reranking is extracting the actual
    # text strings of the ANN LOINC codes and the cosine similarity scores.
    results_list = opensearch_retrieved_scores.hits.hits

    if results_list:
        high_rank_results = [hit for hit in results_list if hit.score >= HIGH_RANK_THRESHOLD]
        retrieved_loinc_names = [hit.source.description for hit in results_list]
        retriever_scores = [hit.score for hit in results_list]

        use_reranker_result = True
        prune_before_ranking = True

        # Case 1: We have a leading perfect score in the OpenSearch hits, which
        # means the top candidate is a verbatim LOINC code string (either directly
        # entered, or found via auto-map). In either case, no need to rerank.
        # Ignore the ruff rule here because explicitly spelling out these cases
        # improves logic readability.
        if retriever_scores[0] >= 1.0:  # noqa: SIM114
            use_reranker_result = False
            top_result = results_list[0]

        # Case 2: The highest scoring search result exceeds the "leader margin,"
        # meaning the sum of its similarity score _plus_ the margin by which it
        # exceeds the second highest scoring result is greater than the threshold
        # required for auto-classification. As above, we will just use the result.
        elif 2.0 * retriever_scores[0] - retriever_scores[1] >= LEADER_MARGIN:
            use_reranker_result = False
            top_result = results_list[0]

        # Case 3: We have enough candidates with high retriever scores to perform
        # high-threshold reranking, which performs reranking only on those
        # candidates who pass the "high-rank" threshold. Note that in this case,
        # we do not perform additional margin-based pruning.
        elif len(high_rank_results) >= MINIMUM_HITS_TO_HIGH_RANK:
            retrieved_loinc_names = [hit.source.description for hit in high_rank_results]
            retriever_scores = [hit.score for hit in high_rank_results]
            prune_before_ranking = False

        # Case 4 (Default): In the absence of a perfect match, a leader candidate,
        # or high-rank thresholding, we'll perform normal reranking using
        # adaptive margin pruning.
        ranked_results = rerank(
            selected_candidate.value,
            retriever_scores,
            retrieved_loinc_names,
            use_pruning=prune_before_ranking,
        )

        if ranked_results:
            if use_reranker_result:
                top_result = next(
                    (
                        x
                        for x in results_list
                        if x.source.description == ranked_results[0]["code_string"]
                    ),
                )

            new_translation = Code(
                code=top_result.source.loinc_code,
                code_system=LOINC_OID,
                code_system_name=LOINC_NAME,
                display_name=top_result.source.description,
                original_text=selected_candidate.value,
            )

            # Make sure we save the results of a successful standardization
            # into the results cache for future use
            put_new_cached_result(
                opensearch_client=opensearch_client,
                index=RESULT_CACHE_INDEX,
                candidate_input=selected_candidate.value,
                data_field=data_field,
                loinc_code=new_translation,
                search_score=top_result.score,
                reranker_score=ranked_results[0]["score"],
                opensearch_retrieved_scores=opensearch_retrieved_scores,
                reranker_processed_results=ranked_results,
                cache_key=cache_key,
            )
        else:
            unmatched_message = "Reranker did not return any results."
    else:
        unmatched_message = "Opensearch query returned no hits."

    return new_translation, unmatched_message, opensearch_retrieved_scores, ranked_results


def _build_schematron_error_work_items(
    processor: eicr_processor.EicrProcessor,
    schematron_data_fields: list[SchematronErrorDetail],
) -> list[_ErrorWork]:
    """Phase 1: extract and select a candidate per error (CPU only).

    :param processor: The eICR processor instance.
    :param schematron_data_fields: The list of Schematron errors to process.
    :return: A list of _ErrorWork items, one per Schematron error.
    """
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

    return work_items


def _load_cached_results(
    work_items: list[_ErrorWork],
    opensearch_client: OpenSearch,
) -> None:
    """Phase 2: Before the full embedding, searching, and reranking process, check all candidates against the result cache in one mget.

    Load all cached results for the selected candidates.

    :param work_items: The list of _ErrorWork items to process.
    :param opensearch_client: The OpenSearch client.
    """
    cache_keys = [work.cache_key for work in work_items if work.cache_key is not None]
    if not cache_keys:
        return

    cached_results = get_cached_results(opensearch_client, RESULT_CACHE_INDEX, cache_keys)
    for work in work_items:
        if work.cache_key is not None:
            work.cached_result = cached_results.get(work.cache_key)


def _embed_cache_misses(work_items: list[_ErrorWork]) -> None:
    """Phase 3: embed the cache-miss candidates in one batched encode call.

    Errors that share a cache key share one resolution in phase 4, so only the first occurrence of each missing key is embedded.

    :param work_items: The list of _ErrorWork items to process.
    """
    cache_misses: list[_ErrorWork] = []
    miss_texts: list[str] = []
    miss_keys: set[str] = set()
    for work in work_items:
        if work.selected_candidate is None or work.cached_result is not None:
            continue
        if work.cache_key is None or work.cache_key in miss_keys:
            continue
        miss_keys.add(work.cache_key)
        cache_misses.append(work)
        miss_texts.append(work.selected_candidate.value)

    if not cache_misses:
        return

    logger.info(
        "Embedding the relevant text strings for each error in the eICR",
        status="processing",
    )
    embeddings = embed_batch(miss_texts)
    for work, vector in zip(cache_misses, embeddings, strict=True):
        work.embedding = vector.tolist()


def _resolve_work_item(
    work: _ErrorWork,
    resolved_misses: dict[str, _CandidateResolution],
    opensearch_client: OpenSearch,
) -> _CandidateResolution:
    """Resolve one error from the cache or through OpenSearch and reranking.

    :param work: The _ErrorWork item to resolve.
    :param resolved_misses: A dict of cache-miss resolutions, keyed by cache key.
    :param opensearch_client: The OpenSearch client.
    :return: The resolved _CandidateResolution for the error.
    """
    selected_candidate = work.selected_candidate
    if selected_candidate is None:
        return _CandidateResolution(unmatched_message="No candidate found.")

    # We've got a hit--no need to run our usual processes, we'll
    # just pull out the fields we want to use directly
    if work.cached_result is not None:
        logger.info("Cache hit, retrieving cached results", status="processing")
        _record_cache_metric(HitValue.hit)
        cached_result = work.cached_result
        return _CandidateResolution(
            new_translation=cached_result.loinc_code,
            opensearch_retrieved_scores=cached_result.opensearch_retrieved_scores,
            ranked_results=cached_result.reranker_processed_results["results"],
        )

    # Cache miss, so run everything normally, and then finally store
    # the prediction in the cache for future use
    if work.cache_key is None:
        # Should be unreachable: phase 1 computes a key for every candidate.
        raise ValueError(f"Missing cache key for candidate: {selected_candidate.value}")

    if work.cache_key in resolved_misses:
        resolution = resolved_misses[work.cache_key]
        _record_cache_metric(
            HitValue.hit if resolution.new_translation is not None else HitValue.miss
        )
        return resolution

    _record_cache_metric(HitValue.miss)
    if work.embedding is None:
        # Unreachable: phase 3 embeds every cache-miss candidate.
        raise ValueError(f"Missing embedding for cache-miss candidate: {selected_candidate.value}")

    (
        new_translation,
        unmatched_message,
        opensearch_retrieved_scores,
        ranked_results,
    ) = _match_candidate(
        selected_candidate,
        work.embedding,
        work.error.field,
        work.cache_key,
        opensearch_client,
    )
    resolution = _CandidateResolution(
        new_translation=new_translation,
        unmatched_message=unmatched_message,
        opensearch_retrieved_scores=opensearch_retrieved_scores,
        ranked_results=ranked_results,
    )
    resolved_misses[work.cache_key] = resolution
    return resolution


def _resolve_error_work_items(
    work_items: list[_ErrorWork],
    opensearch_client: OpenSearch,
) -> tuple[list[TTCSchematronIssueDetail], list[NonstandardCodeInstance]]:
    """Phase 4: Resolve all errors and assemble TTC details in their original order.

    Resolve each error - from the cache when hit, otherwise via KNN search + rerank — and assemble details in the original error order.
    Duplicate candidates reuse the first occurrence's resolution, mirroring the sequential flow where later duplicates hit the cache entry written moments earlier — including in the cache metric, which counts a reused successful match as a hit.

    :param work_items: The list of _ErrorWork items to process.
    :param opensearch_client: The OpenSearch client.
    :return: A tuple of (list of TTCSchematronIssueDetail, list of NonstandardCodeInstance).
    """
    resolved_misses: dict[str, _CandidateResolution] = {}
    issue_details: list[TTCSchematronIssueDetail] = []
    nonstandard_code_replacements: list[NonstandardCodeInstance] = []

    for work in work_items:
        error = work.error
        resolution = _resolve_work_item(work, resolved_misses, opensearch_client)

        if resolution.new_translation is not None:
            nonstandard_code_replacements.append(
                NonstandardCodeInstance(
                    schematron_error_xpath=error.error_context,
                    field_type=error.field,
                    new_translation=resolution.new_translation,
                ),
            )

        issue_details.append(
            TTCSchematronIssueDetail(
                candidate=work.selected_candidate,
                field_type=error.field,
                issue_context=error.error_context,
                issue_id=error.error_id,
                issue_message=error.error_message,
                issue_test=error.error_test,
                unmatched_reason=resolution.unmatched_message,
                new_translation=resolution.new_translation,
                opensearch_retrieved_scores=resolution.opensearch_retrieved_scores,
                reranker_processed_results=resolution.ranked_results,
            ),
        )

    return issue_details, nonstandard_code_replacements


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
    - Processing the eICR for TTC, which includes:
        - Evaluating candidates and selecting relevant text for each error in the eICR
        - Embedding the relevant text string for each error in the eICR
        - Querying OpenSearch with the relevant text string and retrieving the code suggestions
        - Reranking the code suggestions based on relevance to the error and returning the top suggestion
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
        work_items = _build_schematron_error_work_items(processor, schematron_data_fields)
        _load_cached_results(work_items, opensearch_client)
        _embed_cache_misses(work_items)
        (
            ttc_schematron_issues_details,
            nonstandard_code_replacements,
        ) = _resolve_error_work_items(work_items, opensearch_client)
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
        model_info=TTCModelInfo(
            retriever=RETRIEVER_MODEL_INFO,
            reranker=RERANKER_MODEL_INFO,
        ),
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


def _validate_opensearch_index(opensearch_client: OpenSearch) -> None:
    """Validate that the TTC OpenSearch index exists and contains documents.

    :param opensearch_client: The OpenSearch client.
    """
    if not opensearch_client.indices.exists(index=OPENSEARCH_INDEX):
        logger.error(
            "TTC OpenSearch index unavailable",
            index_name=OPENSEARCH_INDEX,
            index_status="missing",
            status="error",
        )
        raise RuntimeError(f"TTC OpenSearch index unavailable: {OPENSEARCH_INDEX} does not exist")

    document_count = int(opensearch_client.count(index=OPENSEARCH_INDEX)["count"])
    if document_count == 0:
        logger.error(
            "TTC OpenSearch index unavailable",
            index_name=OPENSEARCH_INDEX,
            index_status="empty",
            document_count=document_count,
            status="error",
        )
        raise RuntimeError(f"TTC OpenSearch index unavailable: {OPENSEARCH_INDEX} is empty")
