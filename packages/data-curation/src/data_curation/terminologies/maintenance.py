from datetime import datetime

from data_curation.terminologies.general import (
    TerminologyUpdateResponse,
    get_date_from_filename,
    get_latest_extract_file_name,
    save_jsonl_file,
)
from data_curation.terminologies.loinc import (
    LAB_NAMES,
    extract_full_loinc_lab_names,
    get_loinc_current_version_data,
    get_loinc_embedding_records,
    set_loinc_response,
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
        return set_loinc_response(
            result="error", message="Unable to locate latest LOINC Lab Names Extract"
        )
    # ensure the existing TTC LOINC LabNames file is before the latest LOINC update
    file_date = get_date_from_filename(current_loinc_file, "loinc")
    if file_date <= loinc_version_date:
        loinc_updates = get_loinc_embedding_records(
            loinc_version,
            loinc_version_date,
            current_loinc_file,
        )
    else:
        return set_loinc_response(
            result="success",
            message=f"No updates found for the latest LOINC ({loinc_version}) Version!",
        )

    # add embeddings to any of the records for the various descriptions
    if len(loinc_updates) > 0:
        loinc_response = set_loinc_response(
            result="success",
            message=f"LOINC Lab Name Embedding Records to add: {len(loinc_updates)}",
        )
        for loinc_update_record in loinc_updates:
            if (
                loinc_update_record.get("description") is not None
                and loinc_update_record.get("description", "").strip()
            ):
                embedding = embed(loinc_update_record["description"])
                loinc_update_record["description_vector"] = embedding.tolist()
        ingestion_file_name = f"{LAB_NAMES}_{datetime.now().strftime('%Y%m%d')}.jsonl"
        save_jsonl_file(ingestion_file_name, loinc_updates)

        # if all goes well write a new valueset file with all the existing codes
        extract_full_loinc_lab_names()
    return loinc_response


def main(all: bool = False, loinc: bool = False) -> None:
    """Currently the main entry into the process of updating medical terminologies leveraged by TTC.  We can change this into a different mechanism as we wrap this up into a Lambda.

    :param all: Boolean flag to indicate if you want to perform all
        medical terminology updates.  Defaults to False.
    :param loinc: Boolean flag to indicate if you want to perform just
        LOINC terminology updates.  Defaults to False.

    Returns nothing at this time.
    """
    if all or loinc:
        update_loinc_embeddings()


if __name__ == "__main__":
    main(all=True)
