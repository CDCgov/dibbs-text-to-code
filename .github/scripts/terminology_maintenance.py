import csv
import io
import json
import logging
import os
from datetime import datetime

from data_curation.terminologies.general import (
    BASE_FOLDER,
    TerminologyUpdateResponse,
    get_date_from_file_name,
)
from data_curation.terminologies.loinc import (
    LAB_NAMES,
    extract_full_loinc_lab_names,
    get_loinc_current_version_data,
    get_loinc_embedding_records,
    set_loinc_response,
)

from lambda_handler.lambda_handler import create_s3_client, get_file_content_from_s3, put_file
from text_to_code.services.embedder import embed

S3_BUCKET = os.getenv("S3_BUCKET", "dibbs-text-to-code")
TERMINOLOGY_EXTRACT_PREFIX = os.getenv("TERMINOLOGY_EXTRACT_PREFIX", "Terminologies/")
INGESTION_PREFIX = os.getenv("INGESTION_PREFIX", "ingestion/")
LOINC_NAMES_ORIGINAL_EXTRACT = "loinc_lab_names_20260223.csv"

logger = logging.getLogger(__name__)


def get_latest_extract_file_name(file_name_prefix: str) -> str | None:
    """Process to get the latest ValueSet Extract (csv) file name from the TTC S3 Bucket (Terminologies).

    :param file_name_prefix: The prefix of the file name we are looking for the 'max' of.

    :returns: Either the latest file name with the specified prefix, if found, or None.
    """
    if file_name_prefix is None:
        return None
    s3_client = create_s3_client()
    response = s3_client.list_objects_v2(Bucket=S3_BUCKET, Prefix=TERMINOLOGY_EXTRACT_PREFIX)
    if "Contents" not in response:
        print("ERR - CURRENT FILE NOT FOUND!")
        logger.error(f"No file with prefix {file_name_prefix} under {TERMINOLOGY_EXTRACT_PREFIX}!")
        return None

    file_names = []
    for obj in response["Contents"]:
        key = obj["Key"]
        file_name = key.split("/")[-1]
        print(f"GET FILE NAME: File Name: {file_name}")

        if file_name_prefix in file_name:
            file_names.append(file_name)
    return max(file_names) if file_names else None


def _get_terminology_extract_file(file_name: str) -> dict[str, dict[str, str]]:
    """Function that pulls the specified termnology extract file in the Terminologies S3 Bucket Folder for TTC and returns a dictionary representation of the csv file extract.

    :param file_name: The file name of the extract file you wanted parsed
        into a dictionary from the TTC Terminology S3 Bucket.

    :returns: A dictionary of the data pulled from the terminology extract file.
    """
    if not file_name or file_name == "":
        return {}
    object_key = f"{TERMINOLOGY_EXTRACT_PREFIX}{file_name}"
    extract_file = get_file_content_from_s3(S3_BUCKET, object_key)
    extract_dict = {}
    reader = csv.DictReader(extract_file.splitlines(), delimiter="|")
    extract_dict = {row["code"]: row for row in reader}

    return extract_dict


def upload_jsonl_files(response: TerminologyUpdateResponse) -> TerminologyUpdateResponse:
    """Accepts Terminology Update Response and loads embedding records into JSONL Files and then into the Opensearch ingestion pipeline.

    :param response: The TerminologyUpdateResponse object that contains the
        list of embedding records that need to be used to process into a set
        of JSONL files.

    :returns: Terminology Update Response object that contains terminologies, result, and any messages from the process.
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
                    # TODO: Do we need to transform the json.dumps into some kind of IO
                    # like we do for the full extract file to ensure it writes into S3
                    # properly??
                    jsonl_string = "\n".join(json.dumps(rec) for rec in max_records) + "\n"
                    binary_stream = io.BytesIO(jsonl_string.encode("utf-8"))
                    put_file(
                        file_obj=binary_stream,
                        bucket_name=S3_BUCKET,
                        object_key=ingestion_file_name,
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


def upload_csv_extract_file(file_name: str, contents: list[dict]) -> str:
    """Accepts Valueset Extract record rows and a file name and loads into the Terminology Extract Bucket.

    :param file_name: The name of the extract file to be added to TTC S3 Bucket
    :param contents: The content (list of dict) that should be loaded into a |
        delimited csv file into the TTC S3 Bucket.

    :returns: Message of status of uploading csv extract file.
    """
    if not file_name.strip():
        return "No file name supplied.  Failed to save CSV file!"
    if contents is None or len(contents) == 0:
        return f"Empty file contents!  Failed to save CSV for {file_name}"

    object_key = f"{TERMINOLOGY_EXTRACT_PREFIX}{file_name}"
    csv_buffer = io.StringIO()
    headers = contents[0].keys()
    writer = csv.DictWriter(csv_buffer, fieldnames=headers, delimiter="|")
    writer.writeheader()
    writer.writerows(contents)
    binary_stream = io.BytesIO(csv_buffer.getvalue().encode("utf-8"))
    try:
        put_file(
            file_obj=binary_stream,
            bucket_name=S3_BUCKET,
            object_key=object_key,
        )
        return f"Full Extract File {file_name} successfully added to S3 Bucket!"
    except Exception as error:
        return f"Unable to load file {file_name} in Terminologies in S3 Bucket!\n{error}"


def update_loinc() -> TerminologyUpdateResponse:
    """Process to get the latest updates from LOINC and convert all the new loinc codes as well as changes to existing loinc codes into embedding records that can be uploaded into TTC Opensearch ingestion pipeline.

    :returns: Terminology Update Response object that contains terminologies, result, and any messages
    """
    # only handling loinc lab names, but we can modify this function
    # to handle all other loinc code types in the future
    response = update_loinc_lab_names()
    response = upload_jsonl_files(response)

    if response.get("result") == "success":
        full_loinc_labnames = extract_full_loinc_lab_names()
        full_labnames_file_name = (
            f"{response.get('terminology')}_{datetime.now().strftime('%Y%m%d')}.csv"
        )
        upload_response = upload_csv_extract_file(full_labnames_file_name, full_loinc_labnames)
        response["message"] = f"{response['message']}\n{upload_response}"

    return response


def load_initial_extract_files() -> list[str]:
    """Load all initial extract files from our repo into whatever specified S3 bucket.  This should only need to be run one time.

    :returns: String to indicate success or failure
    """
    results = []
    contents: list[dict] = []
    for file in BASE_FOLDER.iterdir():
        if file.is_file():
            try:
                with open(file, encoding="utf-8") as filecontents:
                    reader = csv.DictReader(filecontents, delimiter="|")
                    contents = list(reader)
                    result = upload_csv_extract_file(file.name, contents)
                results.append(result)
            except Exception as err:
                results.append(str(err))
    return results


def update_loinc_lab_names() -> TerminologyUpdateResponse:
    """Process to get the latest updates from LOINC for Lab Names and convert all the new loinc codes as well as changes to existing loinc codes into embedding records that can be uploaded into TTC Opensearch ingestion pipeline.

    :returns: Terminology Update Response object that contains terminologies, result, and any messages
    """
    # get the latest version number and version date of LOINC
    loinc_version, loinc_version_date = get_loinc_current_version_data()
    # find the existing TTC LOINC LabNames file to use for comparison
    current_loinc_file = get_latest_extract_file_name(LAB_NAMES)
    # if we can't find a 'current' existing loinc_lab_names extract file
    # in our defined terminologies S3 bucket, then add the original extract
    # file from our repo
    if current_loinc_file is None:
        results = load_initial_extract_files()
        logger.info(results)
        current_loinc_file = LOINC_NAMES_ORIGINAL_EXTRACT
        # raise FileNotFoundError("Unable to locate latest LOINC Lab Names Extract file!")
    # ensure the existing TTC LOINC LabNames file is before the latest LOINC update
    file_date = get_date_from_file_name(current_loinc_file, "loinc")
    if file_date <= loinc_version_date:
        current_loinc_file_dict = _get_terminology_extract_file(current_loinc_file)
        loinc_response: TerminologyUpdateResponse = get_loinc_embedding_records(
            loinc_version, loinc_version_date, current_loinc_file_dict, False
        )
        loinc_records = loinc_response.get("embedding_records")
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
            description = loinc_update_record.get("description")
            if description and description.strip() is not None:
                embedding = embed(description)
                loinc_update_record["description_vector"] = embedding.tolist()
    return loinc_response


def main(terminology: str = "all") -> None:
    """Currently the main entry into the process of updating medical terminologies leveraged by TTC.  We can change this into a different mechanism as we wrap this up into a Lambda.

    :param terminology: A string that accepts the name of the terminology
        you need upated.  Defaults to 'all' that will process all terminologies.

    Returns nothing at this time.
    """
    if terminology in ("all", "loinc"):
        response = update_loinc()

    if response.get("change_log") != {}:
        logger.info(response.get("change_log"))
    logger.info(f"{response.get('result')}:\n{response.get('message')}")


if __name__ == "__main__":
    main("all")
