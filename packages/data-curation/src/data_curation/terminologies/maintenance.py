from data_curation.terminologies.general import (
    TerminologyUpdateResponse,
    get_date_from_filename,
    get_latest_extract_file_name,
)
from data_curation.terminologies.loinc import (
    LAB_NAMES,
    LoincUpdateResponse,
    get_loinc_current_version_data,
    get_loinc_embedding_records,
)
from text_to_code.services.embedder import embed


# this current function is just set to work for
# labnames, but can be modified to perform some or all
# of the various LOINC valuesets
def update_loinc_embeddings() -> TerminologyUpdateResponse:
    """Process to get the latest updates from LOINC and convert all the new loinc codes and changes to existing loinc codes into embedding records that can be uploaded into TTC Opensearch.

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
        loinc_response: LoincUpdateResponse = get_loinc_embedding_records(
            loinc_version,
            loinc_version_date,
            current_loinc_file,
        )
    else:
        general_response: TerminologyUpdateResponse = {
            "terminology": ["loinc"],
            "result": "success",
            "message": f"No updates found for the latest LOINC ({loinc_version}) Version!",
            "change_log": {},
        }
        return general_response

    embedding_records = loinc_response["embedding_records"]
    # add embeddings to any of the records for the various descriptions
    if len(embedding_records) > 0:
        for loinc_update_record in embedding_records:
            description = loinc_update_record.get("description", "").strip()
            if description is not None:
                embedding = embed(description)
                loinc_update_record["description_vector"] = embedding.tolist()
        # TODO:
        # use this same filename convention but store these in an
        # S3 Bucket instead of a file locally - this is for the JSONL Files
        #  ingestion_file_name = f"{LAB_NAMES}_{datetime.now().strftime('%Y%m%d')}.jsonl"

        # if all goes well write a new valueset file with all the existing codes
        # TODO: this should be passed back to be written back into S3 Bucket by the LAMBDA

        # TODO: the Lambda then needs to extract and store the FULL
        # LOINC File in S3 as well for the next comparison AND
        # Delete the current extract file
        # extract_full_loinc_lab_names()
    return loinc_response


def update_terminology_embeddings(
    all: bool = False, loinc: bool = False
) -> TerminologyUpdateResponse:
    """Currently the main entry into the process of updating medical terminologies leveraged by TTC.  We can change this into a different mechanism as we wrap this up into a Lambda.

    :param all: Boolean flag to indicate if you want to perform all
        medical terminology updates.  Defaults to False.
    :param loinc: Boolean flag to indicate if you want to perform just
        LOINC terminology updates.  Defaults to False.

    Returns nothing at this time.
    """
    if all or loinc:
        response = update_loinc_embeddings()
    return response
