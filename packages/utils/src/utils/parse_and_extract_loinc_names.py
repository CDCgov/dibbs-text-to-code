# Shared utils for all things model extraction, loading, and fine-tuning.


def parse_snoinc_extracts(
    extract_path: str,
    short_name_col: int = 1,
    long_name_col: int = 2,
    display_name_col: int = 3,
    skip_first: bool = True,
):
    """
    Given a path to an extract file of information on various LOINC codes,
    parse the rows of that file in to three discrete lists corresponding to
    the long common names, short names, and display names of those codes.
    The file is expected to be a pipe-delimited text file in which each
    LOINC code is expected to represent a single line.

    :param extract_path: The path to the extract file to parse.
    :param short_name_col: The column of the pipe file containing the
      short name for a given LOINC code.
    :param long_name_col: The column of the pipe file containing the long
      common name for a given LOINC code.
    :param display_name_col: The column of the pipe file containing the
      display name for a given LOINC code.
    :param skip_first: Optionally, a boolean indicating whether to skip the
      first line of the file, if it is a header row.
    :returns: A tuple of three lists, one for eaech name variant.
    """
    long_common_names = []
    short_names = []
    display_names = []

    with open(extract_path, "r", encoding="utf-8") as fp:
        lines_seen = 0
        for line in fp:
            if lines_seen == 0:
                lines_seen += 1
                if skip_first:
                    continue
            if line.strip() != "":
                names = line.strip().split("|")
                # Skip lines that aren't real entries (formatting artifacts)
                if len(names) >= 4:
                    long_common_names.append(names[long_name_col].strip())
                    short_names.append(names[short_name_col].strip())
                    display_names.append(names[display_name_col].strip())

    for name_list in [long_common_names, short_names, display_names]:
        name_list = [x for x in name_list if not x == ""]

    return long_common_names, short_names, display_names
