import io
import json
import os
from dataclasses import dataclass
from datetime import UTC
from datetime import datetime
from typing import Literal

from aws_lambda_powertools import Logger
from aws_lambda_powertools.utilities.data_classes import SQSEvent
from aws_lambda_powertools.utilities.data_classes import event_source
from aws_lambda_powertools.utilities.typing import LambdaContext
from pydantic import BaseModel
from pydantic import ConfigDict

import lambda_handler
from lambda_handler.models import OpenSearchResult
from shared_models import Code
from shared_models import DataField
from shared_models import NonstandardCodeReplacement
from shared_models import TTCOutput
from text_to_code.models import Candidate
from text_to_code.models import query as query_models
from text_to_code.models.eicr import Metadata as EICRMetadata
from text_to_code.services import eicr_processor
from text_to_code.services import evaluator
from text_to_code.services import schematron_processor
from text_to_code.services.embedder import embed
from text_to_code.services.query import QueryBuilder
from text_to_code.services.reranker import ScoredResult
from text_to_code.services.reranker import rerank

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

# Constants
NO_DATA_FIELDS_MESSAGE = (
    "No relevant data fields identified from Schematron errors for TTC processing"
)


@dataclass
class TTCSchematronIssueDetail:
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


class TTCMetadata(BaseModel):
    """Model to hold metadata about the TTC process."""

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    eicr_metadata: EICRMetadata | None
    persistence_id: str
    ttc_schematron_issues: list[TTCSchematronIssueDetail]
    processed_at: datetime
    reason_for_skipping: (
        Literal["No relevant data fields identified from Schematron errors for TTC processing"]
        | None
    ) = None


@dataclass
class Failure:
    """Simple dataclass of the data describing a failure that is sent in the Lambda handler response."""

    message_id: str
    error: str


class FailureResponse(BaseModel):
    """Response given by the Lambda handler when one more more failures occur."""

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    status_code: Literal[200] = 200
    message: Literal["TTC processed with some failures!"] = "TTC processed with some failures!"
    failures: list[Failure]
    num_failure_eicrs: int
    num_success_eicrs: int


class SuccessResponse(BaseModel):
    """Response given by the Lambda handler when no failures occur."""

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    status_code: Literal[200] = 200
    message: Literal["TTC processed successfully!"] = "TTC processed successfully!"
    num_success_eicrs: int


@event_source(data_class=SQSEvent)
@logger.inject_lambda_context
def handler(event: SQSEvent, context: LambdaContext) -> SuccessResponse | FailureResponse:
    """Text to Code lambda entry point.

    :param event: The SQS event containing the S3 event data for processing.
    :param context: The Lambda context object.
    :return: A dictionary containing the status code, message, and any relevant data about the processing results.
    """
    logger.info("Received event", record_count=len(event["Records"]), status="processing")

    failures: list[Failure] = []
    successes: list[str] = []

    opensearch_client = lambda_handler.create_opensearch_client()
    s3_client = lambda_handler.create_s3_client()

    for record in event.records:
        try:
            if not record.body:
                logger.warning("Empty SQS body", message_id=record.message_id, status="skipped")
                continue

            # Parse the EventBridge S3 event from the SQS message body
            s3_event = json.loads(record.body)
            bucket_name, object_key = lambda_handler.get_eventbridge_data_from_s3_event(s3_event)

            if not bucket_name:
                raise ValueError(
                    "No bucket name found in S3 event payload. "
                    "The TTC lambda derives its target bucket from the event and does not use a "
                    "static bucket configuration. Ensure the EventBridge/S3 event includes "
                    "detail.bucket.name.",
                )

            # Extract persistence_id from the RR object key
            persistence_id = lambda_handler.get_persistence_id(object_key, TTC_INPUT_PREFIX)

            with logger.append_context_keys(
                persistence_id=persistence_id,
                bucket_name=bucket_name,
                trigger_s3_key=object_key,
            ):
                logger.info("Starting TTC processing", status="processing")

                object_key = f"{TTC_INPUT_PREFIX}{persistence_id}"
                logger.info(
                    "Retrieving eICR from S3",
                    bucket_name=bucket_name,
                    s3_key=object_key,
                    status="processing",
                )
                original_eicr_content = lambda_handler.get_file_content_from_s3(
                    bucket_name=bucket_name,
                    object_key=object_key,
                    s3_client=s3_client,
                )
                logger.info("Retrieved eICR content", status="success")

                processor = eicr_processor.EicrProcessor(original_eicr_content)

                logger.info(
                    "Loading Schematron errors",
                    bucket_name=bucket_name,
                    s3_key=object_key,
                    status="processing",
                )

                object_key = f"{SCHEMATRON_ERROR_PREFIX}{persistence_id}"
                all_schematron_issues = lambda_handler.get_file_content_from_s3(
                    bucket_name=bucket_name,
                    object_key=object_key,
                    s3_client=s3_client,
                )

                # Process Schematron errors to identify relevant data fields for TTC processing
                ttc_schematron_issues = schematron_processor.get_data_fields_from_schematron_error(
                    all_schematron_issues,
                )

                if not ttc_schematron_issues:
                    logger.warning(
                        "No errors relevant to TTC found in the Schematron output.",
                        status="skipped",
                    )
                    logger.info("TTC processing completed", status="no_matches_found")

                    ttc_metadata = TTCMetadata(
                        eicr_metadata=processor.eicr_metadata,
                        persistence_id=persistence_id,
                        ttc_schematron_issues=[],
                        processed_at=datetime.now(UTC),
                        reason_for_skipping="No relevant data fields identified from Schematron errors for TTC processing",
                    )

                    metadata_key = (
                        f"{TTC_METADATA_PREFIX}{persistence_id.removesuffix('.xml')}.json"
                    )

                    logger.info(
                        "Saving TTC metadata output to S3",
                        bucket_name=bucket_name,
                        s3_key=metadata_key,
                        status="processing",
                    )
                    lambda_handler.put_file(
                        file_obj=io.BytesIO(ttc_metadata.model_dump_json().encode("utf-8")),
                        bucket_name=bucket_name,
                        object_key=metadata_key,
                        s3_client=s3_client,
                    )
                    logger.info(
                        "Saved TTC metadata output to S3",
                        bucket_name=bucket_name,
                        s3_key=metadata_key,
                        status="success",
                    )

                    continue

                nonstandard_code_replacements: list[NonstandardCodeReplacement] = []
                ttc_schematron_issues_details: list[TTCSchematronIssueDetail] = []
                for ttc_issue in ttc_schematron_issues:
                    unmatched_message = None
                    opensearch_retrieved_scores = None
                    ranked_results = None
                    field_type = ttc_issue.field

                    text_candidates = processor.get_text_candidates(
                        ttc_issue.error_context,
                        field_type,
                    )

                    logger.info(
                        "Evaluating candidates and selecting relevant text for each error in the eICR",
                        status="processing",
                    )

                    selected_candidate = evaluator.select_relevant_text(
                        candidates=text_candidates,
                        field_type=field_type,
                    )

                    logger.info(
                        "Embedding the relevant text strings for each error in the eICR",
                        status="processing",
                    )

                    if selected_candidate:
                        vector_embedding = embed(selected_candidate.value)

                        vector_parameters = query_models.VectorSearchParams(
                            vector=vector_embedding.tolist(),
                            data_field=field_type,
                        )

                        logger.info(
                            "Querying OpenSearch with the relevant text strings and retrieving code suggestions",
                            status="processing",
                        )
                        query = QueryBuilder().with_vector_search(vector_parameters).build()

                        opensearch_retrieved_scores = lambda_handler.retrieve_opensearch_results(
                            query=query,
                            index=OPENSEARCH_INDEX,
                            opensearch_client=opensearch_client,
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
                                )
                                new_translation_with_text = new_translation.model_copy(
                                    update={"original_text": selected_candidate.value},
                                )
                                nonstandard_code_replacements.append(
                                    NonstandardCodeReplacement(
                                        schematron_error_xpath=ttc_issue.error_context,
                                        field_type=ttc_issue.field,
                                        new_translation=new_translation_with_text,
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
                            field_type=ttc_issue.field,
                            issue_context=ttc_issue.error_context,
                            issue_id=ttc_issue.error_id,
                            issue_message=ttc_issue.error_message,
                            issue_test=ttc_issue.error_test,
                            unmatched_reason=unmatched_message,
                            new_translation=None,
                            opensearch_retrieved_scores=opensearch_retrieved_scores,
                            reranker_processed_results=ranked_results,
                        ),
                    )

                ttc_output = TTCOutput(
                    persistence_id=persistence_id,
                    nonstandard_codes=nonstandard_code_replacements,
                )

                ttc_metadata = TTCMetadata(
                    eicr_metadata=processor.eicr_metadata,
                    persistence_id=persistence_id,
                    ttc_schematron_issues=ttc_schematron_issues_details,
                    processed_at=datetime.now(UTC),
                )

                # Save the TTC output to S3 for the Augmentation Lambda to consume
                logger.info(
                    "Saving TTC output to S3",
                    bucket_name=bucket_name,
                    s3_key=f"{TTC_OUTPUT_PREFIX}{persistence_id}",
                    status="processing",
                )
                lambda_handler.put_file(
                    file_obj=io.BytesIO(ttc_output.model_dump_json().encode("utf-8")),
                    bucket_name=bucket_name,
                    object_key=f"{TTC_OUTPUT_PREFIX}{persistence_id}",
                    s3_client=s3_client,
                )
                logger.info(
                    "Saved TTC output to S3",
                    bucket_name=bucket_name,
                    s3_key=f"{TTC_OUTPUT_PREFIX}{persistence_id}",
                    status="success",
                )

                metadata_key = f"{TTC_METADATA_PREFIX}{persistence_id.removesuffix('.xml')}.json"

                logger.info(
                    "Saving TTC metadata output to S3",
                    bucket_name=bucket_name,
                    s3_key=metadata_key,
                    status="processing",
                )
                lambda_handler.put_file(
                    file_obj=io.BytesIO(ttc_metadata.model_dump_json().encode("utf-8")),
                    bucket_name=bucket_name,
                    object_key=metadata_key,
                    s3_client=s3_client,
                )
                logger.info(
                    "Saved TTC metadata output to S3",
                    bucket_name=bucket_name,
                    s3_key=metadata_key,
                    status="success",
                )

            successes.append(record.message_id)
        except Exception as e:
            logger.exception(
                "Error processing record",
                message_id=record.message_id,
                status="error",
            )
            failures.append(Failure(record.message_id, str(e)))

    num_failures = len(failures)
    num_successes = len(successes)
    response = (
        FailureResponse(
            failures=failures, num_failure_eicrs=num_failures, num_success_eicrs=num_successes
        )
        if failures
        else SuccessResponse(num_success_eicrs=num_successes)
    )

    logger.info(
        "TTC invocation completed",
        status="partial_failure" if failures else "success",
        num_failure_eicrs=len(failures),
        num_success_eicrs=len(successes),
    )

    return response
