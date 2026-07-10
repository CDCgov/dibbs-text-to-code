import datetime
import json
import logging
import os
from typing import BinaryIO

import boto3
from boto3 import BaseClient
from data_curation.terminologies.general import TerminologyUpdateResponse, get_date_from_filename
from data_curation.terminologies.loinc import (
    LAB_NAMES,
    LOINC_CS_NAMES,
    LoincRow,
    get_loinc_current_version_data,
    get_loinc_embedding_records,
    set_loinc_response,
)

from text_to_code.services.embedder import embed

REGION = AWS_REGION = os.getenv("AWS_REGION", "us-east-1")
S3_BUCKET = os.getenv("S3_BUCKET", "dibbs-text-to-code")
TERMINOLOGY_EXTRACT_PREFIX = os.getenv("TERMINOLOGY_EXTRACT_PREFIX", "Terminologies/")
INGESTION_PREFIX = os.getenv("INGESTION_PREFIX", "ingestion/")

logger = logging.getLogger(__name__)
_cached_s3_client: BaseClient | None = None


def create_s3_client() -> BaseClient:
    """Creates an S3 client.

    :return: S3 client
    """
    global _cached_s3_client  # noqa: PLW0603

    if _cached_s3_client is None:
        # endpoint_url = os.getenv("S3_ENDPOINT_URL")
        region_name = REGION
        _cached_s3_client = boto3.client(
            "s3",
            # endpoint_url=endpoint_url,
            region_name=region_name,
        )
        logger.info("Created S3 client", status="success")

    return _cached_s3_client


def get_file_content_from_s3(bucket_name: str, object_key: str) -> str:
    """Extracts the file content from an S3 bucket.

    :param bucket_name: The name of the S3 bucket.
    :param object_key: The key of the S3 object.
    :return: The content of the file as a string.
    """
    client = create_s3_client()

    logger.info(
        "Retrieving file content from S3",
        bucket_name=bucket_name,
        s3_key=object_key,
        status="processing",
    )
    response = client.get_object(Bucket=bucket_name, Key=object_key)
    logger.info(
        "Retrieved file content from S3",
        bucket_name=bucket_name,
        s3_key=object_key,
        status="success",
    )
    return response["Body"].read().decode("utf-8")


def get_latest_extract_file_name(filename_prefix: str) -> str | None:
    """Process to get t."""
    if filename_prefix is None:
        return None
    s3_client = boto3.resource("s3")
    bucket = s3_client.Bucket(S3_BUCKET)
    files = [
        f
        for f in bucket.objects.filter(Prefix=TERMINOLOGY_EXTRACT_PREFIX)
        if f.key.startswith(filename_prefix)
    ]
    if filename_prefix != "" and files:
        latest_file = max(files)
        return latest_file
    logger.error(f"No file with prefix {filename_prefix} under {TERMINOLOGY_EXTRACT_PREFIX}!")
    return None


def put_file(file_obj: BinaryIO, bucket_name: str, object_key: str) -> None:
    """Uploads a file object to a S3 bucket.

    :param file_obj: The file object to upload.
    :param bucket_name: The name of the S3 bucket to upload to.
    :param object_key: The key to assign to the uploaded object in S3.
    """
    client = create_s3_client()
    logger.info(
        "Uploading file to S3",
        bucket_name=bucket_name,
        s3_key=object_key,
        status="processing",
    )
    client.put_object(Body=file_obj, Bucket=bucket_name, Key=object_key)
    logger.info(
        "Uploaded file to S3",
        bucket_name=bucket_name,
        s3_key=object_key,
        status="success",
    )


def _get_loinc_consumer_names(loinc_rows: list[LoincRow]) -> list[LoincRow]:
    """Function that utilizes the consumer_names.csv file in the Terminologies S3 Bucket Folder for TTC to related the consumer name term with each loinc code.

    :param loinc_rows: The list of dictionaries that contain all the LOINC
        data (codes, terms/names, and axis information) so that this function
        can add the consumer name data to each record.

    :returns: The updated list of dictionaries of LOINC data records with
        the newly added consumer name term(s).
    """
    cs_names = {}
    object_key = f"{TERMINOLOGY_EXTRACT_PREFIX}{LOINC_CS_NAMES}"
    cs_names_file = get_file_content_from_s3(S3_BUCKET, object_key)
    for cs_row in cs_names_file.splitlines():
        cs_code = cs_row.get("LoincNumber")
        cs_name = cs_row.get("ConsumerName")
        if cs_code and cs_name:
            cs_names[cs_code] = cs_name

    for row in loinc_rows:
        loinc_code = row.get("code")
        cs_name = cs_names.get(loinc_code)
        if cs_name:
            row["consumer_name"] = cs_name
        else:
            row["consumer_name"] = None
    return loinc_rows


def load_jsonl_files(response: TerminologyUpdateResponse) -> TerminologyUpdateResponse:
    """Accepts Terminology Update Response and loads embedding records into JSONL Files and then into the Opensearch ingestion pipeline.

    :returns: Terminology Update Response object that contains terminologies, result, and any messages
    """
    record_max = 1000

    embedding_records = response.get("embedding_records")

    if response.get("result") == "success" and embedding_records and len(embedding_records) > 0:
        record_count = 1
        max_records = []
        for emb_rec in embedding_records:
            record_count += 1
            max_records.append(emb_rec)

            if record_count % record_max == 0 or record_count == len(embedding_records):
                ingestion_file_name = f"{INGESTION_PREFIX}{response.get('terminology')}_{datetime.now().strftime('%Y%m%d')}_{record_count}.jsonl"
                try:
                    put_file(
                        (json.dumps(doc) + "\n" for doc in max_records),
                        S3_BUCKET,
                        ingestion_file_name,
                    )
                    max_records = []
                    response["message"] = (
                        f"{response['message']}\nFile {ingestion_file_name} successfully added to Opensearch Ingestion Pipeline!"
                    )
                except Exception as error:
                    response["result"] = "error"
                    response["message"] = (
                        f"{response['message']}\nUnable to land file {ingestion_file_name} in Opensearch Ingestion Pipeline!\n{error}"
                    )
    return response


def update_loinc() -> TerminologyUpdateResponse:
    """Process to get the latest updates from LOINC and convert all the new loinc codes as well as changes to existing loinc codes into embedding records that can be uploaded into TTC Opensearch ingestion pipeline.

    :returns: Terminology Update Response object that contains terminologies, result, and any messages
    """
    # only handling loinc lab names, but we can modify this function
    # to handle all other loinc code types in the future
    response = update_loinc_lab_names()
    load_jsonl_files(response)

    # if all goes well write a new valueset file with all the existing codes
    # TODO: this should be passed back to be written back into S3 Bucket by the LAMBDA

    # TODO: the Lambda then needs to extract and store the FULL
    # LOINC File in S3 as well for the next comparison AND
    # Delete the current extract file
    # extract_full_loinc_lab_names()

    return response


def update_loinc_lab_names() -> TerminologyUpdateResponse:
    """Process to get the latest updates from LOINC for Lab Names and convert all the new loinc codes as well as changes to existing loinc codes into embedding records that can be uploaded into TTC Opensearch ingestion pipeline.

    :returns: Terminology Update Response object that contains terminologies, result, and any messages
    """
    # get the latest version number and version date of LOINC
    loinc_version, loinc_version_date = get_loinc_current_version_data()
    # find the existing TTC LOINC LabNames file to use for comparison
    current_loinc_file = get_latest_extract_file_name(LAB_NAMES)
    if current_loinc_file is None:
        raise FileNotFoundError("Unable to locate latest LOINC Lab Names Extract file!")
    # ensure the existing TTC LOINC LabNames file is before the latest LOINC update
    file_date = get_date_from_filename(current_loinc_file, "loinc")
    if file_date <= loinc_version_date:
        loinc_response: TerminologyUpdateResponse = get_loinc_embedding_records(
            loinc_version, loinc_version_date, current_loinc_file, False
        )
        loinc_records = loinc_response.get("embedding_records")
        loinc_records = _get_loinc_consumer_names(loinc_records)
        loinc_response["embedding_records"] = loinc_records
    else:
        return set_loinc_response(
            LAB_NAMES,
            "success",
            f"No updates found for the latest LOINC ({loinc_version}) Version!",
        )

    embedding_records = loinc_response["embedding_records"]
    # add embeddings to any of the records for the various descriptions
    if len(embedding_records) > 0:
        for loinc_update_record in embedding_records:
            description = loinc_update_record.get("description", "").strip()
            if description is not None:
                embedding = embed(description)
                loinc_update_record["description_vector"] = embedding.tolist()

        # if all goes well write a new valueset file with all the existing codes
        # TODO: this should be passed back to be written back into S3 Bucket by the LAMBDA

        # TODO: the Lambda then needs to extract and store the FULL
        # LOINC File in S3 as well for the next comparison AND
        # Delete the current extract file
        # extract_full_loinc_lab_names()
    return loinc_response


def main(terminology: str = "all") -> None:
    """Currently the main entry into the process of updating medical terminologies leveraged by TTC.  We can change this into a different mechanism as we wrap this up into a Lambda.

    :param all: Boolean flag to indicate if you want to perform all
        medical terminology updates.  Defaults to False.
    :param loinc: Boolean flag to indicate if you want to perform just
        LOINC terminology updates.  Defaults to False.

    Returns nothing at this time.
    """
    if terminology in ("all", "loinc"):
        response = update_loinc()

    change_log = response.get("change_log")
    print(change_log)
