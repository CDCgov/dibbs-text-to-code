
from data_curation.terminologies.utils.loinc import get_loinc_current_version_data, LAB_NAMES, get_loinc_embedding_candidates
from data_curation.terminologies.utils.general import get_latest_extract_file_name, get_date_from_latest_filename, load_extract_file_to_dict


def update_loinc_embeddings():
    loinc_version, loinc_version_date = get_loinc_current_version_data()
    current_loinc_file = get_latest_extract_file_name(LAB_NAMES)
    file_date = get_date_from_latest_filename(current_loinc_file,"loinc")
    if (file_date <= loinc_version_date):
        print("UPDATE IS A GO!")
        # get the current extract into a dict
        loinc_current_dict = load_extract_file_to_dict(current_loinc_file)
        get_loinc_embedding_candidates(loinc_current_dict,loinc_version)

    else:
        print("DO NOTHING!")


def main():
    update_loinc_embeddings()
    # loinc_data1, loinc_data2 = get_loinc_current_version_data()
    # print(loinc_data1)
    # print(loinc_data2)
    # filename = get_latest_extract_file_name(LAB_NAMES)
    # print(filename)
    # file_date = get_date_from_latest_filename(filename,"loinc")
    # print(file_date)



if __name__ == "__main__":
    main()