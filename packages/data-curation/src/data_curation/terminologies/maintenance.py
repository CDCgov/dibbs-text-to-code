
from data_curation.terminologies.utils.loinc import (get_loinc_current_version_data,
                                                     LAB_NAMES,
                                                     get_loinc_embedding_candidates,
                                                     extract_full_loinc_lab_names)
from data_curation.terminologies.utils.general import (get_latest_extract_file_name, 
                                                       get_date_from_latest_filename, 
                                                       load_extract_file_to_dict,
                                                       archive_valueset_file)
from text_to_code.services.embedder import embed


def update_loinc_embeddings():
    # this current function is just set to work for
    # labnames, but can be modified to perform some or all
    # of the various LOINC valuesets
    loinc_version, loinc_version_date = get_loinc_current_version_data()
    current_loinc_file = get_latest_extract_file_name(LAB_NAMES)
    file_date = get_date_from_latest_filename(current_loinc_file,"loinc")
    if (file_date <= loinc_version_date):
        print(f"Getting all updates from LOINC since {loinc_version_date}!")
        # get the current extract into a dict
        loinc_current_dict = load_extract_file_to_dict(current_loinc_file)
        loinc_updates = get_loinc_embedding_candidates(loinc_current_dict,
                                                       loinc_version,
                                                       loinc_version_date,
                                                       current_loinc_file)

    else:
        print(f"No updates found for the latest LOINC ({loinc_version}) Version!")
    
    # add embeddings to any of the candidates for the various descriptions
    # if there are none, no looping will occur
    my_test = embed("Weed Allerg Mix3 IgE Msmt Ser").tolist()
    print(f"MY TEST: {my_test}")
    
    for loinc_update_record in loinc_updates:
        if (loinc_update_record["description"].strip is not None):
            loinc_update_record["description_vector"] = embed(loinc_update_record["description"])
    
        print(loinc_update_record)
        return
    # if all goes well archive the old file and 
    # write a new valueset file with all the existing codes
    archive_valueset_file(current_loinc_file)
    extract_full_loinc_lab_names()   


def main(all: bool = False, loinc=False):
    if all or loinc:
        update_loinc_embeddings()

if __name__ == "__main__":
    main(all=True)