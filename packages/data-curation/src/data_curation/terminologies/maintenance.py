
from data_curation.terminologies.utils.loinc import (get_loinc_current_version_data,
                                                     LAB_NAMES,
                                                     get_loinc_embedding_candidates)
from data_curation.terminologies.utils.general import (get_latest_extract_file_name, 
                                                       get_date_from_latest_filename, 
                                                       load_extract_file_to_dict)


def update_loinc_embeddings():
    loinc_version, loinc_version_date = get_loinc_current_version_data()
    current_loinc_file = get_latest_extract_file_name(LAB_NAMES)
    file_date = get_date_from_latest_filename(current_loinc_file,"loinc")
    if (file_date <= loinc_version_date):
        print(f"Getting all updates from LOINC since {loinc_version_date}!")
        # get the current extract into a dict
        loinc_current_dict = load_extract_file_to_dict(current_loinc_file)
        loinc_updates = get_loinc_embedding_candidates(loinc_current_dict,loinc_version)

    else:
        print(f"No updates found for the latest LOINC ({loinc_version}) Version!")
    
    if len(loinc_updates) > 0:
        # TODO: now process the updates into embeddings
        # This will be handled in the next ticket
        None

    # TODO: add a function here that will clean up
    # the existing file and make a new one with a new date
    # so that the next time the process is run it will ensure 
    # to not add updates unless they are really necessary
    # 
    # This will be part of the creating the actual embeddings work
    #  It will have to succeed from this step to making the embeddings
    #   into a file or files and then we can update/remove the existing
    # csv file
    


def main(all: bool = False, loinc=False):
    if all or loinc:
        update_loinc_embeddings()

if __name__ == "__main__":
    main(all=True)