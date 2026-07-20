import os
from enum import StrEnum
from io import BytesIO

from aws_lambda_powertools import Logger, Metrics, single_metric
from aws_lambda_powertools.metrics import MetricUnit
from aws_lambda_powertools.utilities.data_classes import SQSEvent, SQSRecord, event_source
from aws_lambda_powertools.utilities.typing import LambdaContext
from opensearchpy import OpenSearch

import lambda_handler
from shared_models import (
    NonstandardCodeInstance,
    PassthroughReason,
    TTCAugmenterInput,
)
from text_to_code.models import OpenSearchResultCacheSource
from text_to_code.models.model_info import TTCModelInfo
from text_to_code.models.schematron import SchematronErrorDetail
from text_to_code.services import eicr_processor, evaluator, schematron_processor
from text_to_code.services.embedder import RETRIEVER_MODEL_INFO
from text_to_code.services.reranker import RERANKER_MODEL_INFO, ScoredResult
from text_to_code.services.result_cache import get_cached_result, put_new_cached_result
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


def _process_schematron_issue(
    error: SchematronErrorDetail,
    processor: eicr_processor.EicrProcessor,
    opensearch_client: OpenSearch,
) -> tuple[TTCSchematronIssueDetail, NonstandardCodeInstance | None]:
    """Attempt to standardize the nonstandard code behind one Schematron error.

    Selects the relevant text candidate from the eICR, then resolves it to a
    LOINC code via the result cache or, on a cache miss, the full matching step
    (embed -> KNN search -> rerank) with the successful result written back to
    the cache.

    :param error: The Schematron error's extracted data fields.
    :param processor: The processor wrapping the parsed original eICR.
    :param opensearch_client: The OpenSearch client.
    :return: The issue detail for the metadata output, and the code replacement
        for the augmenter input (``None`` when no match was found).
    """
    new_translation = None
    unmatched_message = None
    data_field = error.field
    opensearch_retrieved_scores = None
    ranked_results: list[ScoredResult] | None = None
    nonstandard_code: NonstandardCodeInstance | None = None

    text_candidates = processor.get_text_candidates(error.error_context, data_field)

    logger.info(
        "Evaluating candidates and selecting relevant text for each error in the eICR",
        status="processing",
    )

    selected_candidate = evaluator.select_relevant_text(text_candidates, data_field)

    if selected_candidate:
        # Before we run the full embedding, searching, and reranking process,
        # first let's check if we've seen this nonstandard input before
        cache_key = compute_cache_key(selected_candidate.value, data_field)
        cached_result: OpenSearchResultCacheSource | None = get_cached_result(
            opensearch_client, RESULT_CACHE_INDEX, os_doc_id=cache_key
        )

        # We've got a hit--no need to run our usual processes, we'll
        # just pull out the fields we want to use directly
        if cached_result is not None:
            logger.info("Cache hit, retrieving cached results", status="processing")
            _record_cache_metric(HitValue.hit)
            new_translation = cached_result.loinc_code
            opensearch_retrieved_scores = cached_result.opensearch_retrieved_scores
            ranked_results = cached_result.reranker_processed_results["results"]

        # Cache miss, so log that, run everything normally, and then finally store
        # the prediction in the cache for future use
        else:
            logger.info(
                "Embedding the relevant text strings for each error in the eICR",
                status="processing",
            )
            _record_cache_metric(HitValue.miss)
            logger.info(
                "Querying OpenSearch with the relevant text strings and retrieving code suggestions",
                status="processing",
            )
            outcome = match_text(
                selected_candidate.value, data_field, opensearch_client, OPENSEARCH_INDEX
            )
            opensearch_retrieved_scores = outcome.opensearch_results
            ranked_results = outcome.ranked_results

            if isinstance(outcome, Match):
                new_translation = outcome.code
                # Make sure we save the results of a successful standardization
                # into the results cache for future use
                put_new_cached_result(
                    opensearch_client,
                    RESULT_CACHE_INDEX,
                    selected_candidate.value,
                    data_field,
                    new_translation,
                    outcome.top_retriever_score,
                    outcome.ranked_results[0]["score"],
                    outcome.opensearch_results,
                    outcome.ranked_results,
                )
            else:
                unmatched_message = outcome.unmatched_reason

        if new_translation is not None:
            nonstandard_code = NonstandardCodeInstance(
                schematron_error_xpath=error.error_context,
                field_type=error.field,
                new_translation=new_translation,
            )
    else:
        unmatched_message = "No candidate found."

    detail = TTCSchematronIssueDetail(
        candidate=selected_candidate,
        field_type=error.field,
        issue_context=error.error_context,
        issue_id=error.error_id,
        issue_message=error.error_message,
        issue_test=error.error_test,
        unmatched_reason=unmatched_message,
        new_translation=new_translation,
        opensearch_retrieved_scores=opensearch_retrieved_scores,
        reranker_processed_results=ranked_results,
    )
    return detail, nonstandard_code


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
    - Standardizing the code behind each Schematron error (see
      ``_process_schematron_issue``)
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
        for error in schematron_data_fields:
            detail, nonstandard_code = _process_schematron_issue(
                error, processor, opensearch_client
            )
            ttc_schematron_issues_details.append(detail)
            if nonstandard_code is not None:
                nonstandard_code_replacements.append(nonstandard_code)
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
