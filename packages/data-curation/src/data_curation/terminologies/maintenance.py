from data_curation.terminologies.general import (
    get_date_from_filename,
    get_latest_extract_file_name,
    load_extract_file_to_dict,
)
from data_curation.terminologies.loinc import (
    LAB_NAMES,
    get_loinc_current_version_data,
    get_loinc_embedding_records,
)


def update_loinc_embeddings() -> None:
    """Process to get the latest updates from LOINC and convert all the new loinc codes and changes to existing loinc codes into embedding records that can be uploaded into TTC Opensearch.

    Returns nothing at this time.
    TODO: Currently prints out progress and status
        but we will need to convert that to logging statements
        in subsequent PRs
    """
    # get the latest version number and version date of LOINC
    loinc_version, loinc_version_date = get_loinc_current_version_data()
    # find the existing TTC LOINC LabNames file to use for comparison
    current_loinc_file = get_latest_extract_file_name(LAB_NAMES)
    # ensure the existing TTC LOINC LabNames file is before the latest LOINC update
    file_date = get_date_from_filename(current_loinc_file, "loinc")
    if file_date <= loinc_version_date:
        # TODO: In Subsequent PR update this to be a logging statement
        # get the current extract into a dict
        loinc_current_dict = load_extract_file_to_dict(current_loinc_file)
        loinc_updates = get_loinc_embedding_records(loinc_current_dict, loinc_version)
        if len(loinc_updates) > 0:
            # TODO: now process the updates into embeddings
            # This will be handled in the next ticket
            # Handled in Ticket #454
            pass
    else:
        # TODO: In Subsequent PR update this to be a logging statement
        print(f"No updates found for the latest LOINC ({loinc_version}) Version!")
        return

    # TODO: add a function here that will clean up
    # the existing file and make a new one with a new date
    # so that the next time the process is run it will ensure
    # to not add updates unless they are really necessary
    #
    # This will be part of the creating the actual embeddings work
    #  It will have to succeed from this step to making the embeddings
    #   into a file or files and then we can update/remove the existing
    # csv file
    # Handled in Ticket #454


def main(all: bool = False, loinc: bool = False) -> None:
    """Currently the main entry into the process of updating medical terminologies leveraged by TTC.  We can change this into a different mechanism as we wrap this up into a Lambda.

    :param all: Boolean flag to indicate if you want to perform all
        medical terminology updates.  Defaults to False.
    :param loinc: Boolean flag to indicate if you want to perform just
        LOINC terminology updates.  Defaults to False.

    Returns nothing at this time.
    TODO: Currently prints out progress and status
        but we will need to convert that to logging statements
        in subsequent PRs
    """
    if all or loinc:
        update_loinc_embeddings()


if __name__ == "__main__":
    main(all=True)
