import json
import os
from io import BytesIO

from aws_lambda_powertools import Logger
from aws_lambda_powertools.utilities.data_classes import SQSEvent, SQSRecord, event_source
from aws_lambda_powertools.utilities.typing import LambdaContext
from opensearchpy import OpenSearch

import lambda_handler
from shared_models import (
    Code,
    NonstandardCodeInstance,
    PassthroughReason,
    TTCAugmenterInput,
)
from text_to_code.models import query as query_models
from text_to_code.services import eicr_processor, evaluator, schematron_processor
from text_to_code.services.embedder import embed
from text_to_code.services.query import QueryBuilder
from text_to_code.services.reranker import ScoredResult, rerank

from .models.metadata import Metadata, TTCSchematronIssueDetail

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


@event_source(data_class=SQSEvent)
@logger.inject_lambda_context
def handler(event: SQSEvent, context: LambdaContext) -> dict:
    """Text to Code lambda entry point.

    :param event: The SQS event containing the S3 event data for processing.
    :param context: The Lambda context object.
    :return: A dictionary containing the status code, message, and any relevant data about the processing results.
    """
    opensearch_client = lambda_handler.create_opensearch_client()

    logger.info("Received event", record_count=len(event["Records"]), status="processing")

    failures = []
    successes = []

    for record in event.records:
        try:
            process_record(record, opensearch_client)
            successes.append(record.message_id)
        except Exception as e:
            logger.exception(
                "Error processing record",
                message_id=record.message_id,
                status="error",
            )
            passthrough_written = _write_ttc_exception_passthrough_output(record, e)
            if passthrough_written:
                successes.append(record.message_id)
            else:
                failures.append({"message_id": record.message_id, "error": str(e)})

    result = (
        {
            "statusCode": 200,
            "message": "TTC processed with some failures!",
            "failures": failures,
            "num_failure_eicrs": len(failures),
            "num_success_eicrs": len(successes),
        }
        if failures
        else {
            "statusCode": 200,
            "message": "TTC processed successfully!",
            "num_success_eicrs": len(successes),
        }
    )

    logger.info(
        "TTC invocation completed",
        status="partial_failure" if failures else "success",
        num_failure_eicrs=len(failures),
        num_success_eicrs=len(successes),
    )

    return result


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
            passthrough=True,
            passthrough_reason=PassthroughReason.TTC_EXCEPTION,
            error=str(error),
        )
        ttc_output = TTCAugmenterInput(
            persistence_id=persistence_id,
            passthrough=True,
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


def process_record(record: SQSRecord, opensearch_client: OpenSearch) -> None:
    """Process each SQS record.

    :param record: The SQS record to process
    """
    if not record.body:
        logger.warning("Empty SQS body", message_id=record.message_id, status="skipped")
        return

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
        _process_record_pipeline(persistence_id, opensearch_client, bucket_name)


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


def _process_record_pipeline(
    persistence_id: str,
    opensearch_client: OpenSearch,
    bucket_name: str,
) -> None:
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
    ttc_schematron_issues_details = None
    nonstandard_code_replacements: list[NonstandardCodeInstance] = []
    if schematron_data_fields:
        ttc_schematron_issues_details: list[TTCSchematronIssueDetail] = []
        passthrough_reason: PassthroughReason | None = None
        for error in schematron_data_fields:
            new_translation = None
            unmatched_message = None
            data_field = error.field
            opensearch_retrieved_scores = None
            ranked_results: list[ScoredResult] | None = None

            text_candidates = processor.get_text_candidates(error.error_context, data_field)

            logger.info(
                "Evaluating candidates and selecting relevant text for each error in the eICR",
                status="processing",
            )

            selected_candidate = evaluator.select_relevant_text(text_candidates, data_field)

            logger.info(
                "Embedding the relevant text strings for each error in the eICR",
                status="processing",
            )

            if selected_candidate:
                vector_embedding = embed(selected_candidate.value)

                vector_parameters = query_models.VectorSearchParams(
                    vector=vector_embedding.tolist(), data_field=data_field
                )

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
                # text strings of the ANN LOINC codes
                results_list = opensearch_retrieved_scores.hits.hits
                if results_list:
                    retrieved_loinc_names = [hit.source.description for hit in results_list]
                    ranked_results = rerank(selected_candidate.value, retrieved_loinc_names)

                    top_result = next(
                        (
                            x
                            for x in results_list
                            if x.source.description == ranked_results[0]["code_string"]
                        ),
                        None,
                    )

                    if top_result:
                        new_translation = Code(
                            code=top_result.source.loinc_code,
                            code_system="2.16.840.1.113883.6.1",
                            code_system_name="LOINC",
                            display_name=top_result.source.description,
                            original_text=selected_candidate.value,
                        )
                        nonstandard_code_replacements.append(
                            NonstandardCodeInstance(
                                schematron_error_xpath=error.error_context,
                                field_type=error.field,
                                new_translation=new_translation,
                            ),
                        )
                    else:
                        unmatched_message = "Reranker did not return any results."
                else:
                    unmatched_message = "Opensearch query returned no hits."
            else:
                unmatched_message = "No candidate found."

            ttc_schematron_issues_details.append(
                TTCSchematronIssueDetail(
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
                ),
            )
    else:
        passthrough_reason = PassthroughReason.NO_RELEVANT_SCHEMATRON_ERRORS

    if ttc_schematron_issues_details and all(
        x.unmatched_reason for x in ttc_schematron_issues_details
    ):
        passthrough_reason = PassthroughReason.NO_CODE_MATCHES

    ttc_output = TTCAugmenterInput(
        persistence_id=persistence_id,
        nonstandard_codes=nonstandard_code_replacements,
        passthrough=passthrough_reason is not None,
        passthrough_reason=passthrough_reason,
    )
    ttc_metadata = Metadata(
        persistence_id=persistence_id,
        eicr_metadata=processor.eicr_metadata,
        ttc_schematron_issues=ttc_schematron_issues_details,
        passthrough=passthrough_reason is not None,
        passthrough_reason=passthrough_reason,
    )

    _save_outputs(persistence_id, bucket_name, ttc_output, ttc_metadata)

    logger.info(
        "TTC processing completed",
        status="matched" if ttc_output.nonstandard_codes else "no_matches_found",
        passthrough_reason=passthrough_reason,
    )


def _save_outputs(
    persistence_id: str, bucket_name: str, ttc_output: TTCAugmenterInput, ttc_metadata: Metadata
) -> None:
    _save_ttc_outputs(persistence_id, ttc_output, bucket_name)
    _save_ttc_metadata_output(
        persistence_id,
        ttc_metadata,
        bucket_name,
    )
