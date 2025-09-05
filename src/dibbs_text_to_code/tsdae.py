import re
from typing import Union

import spacy

PART_DESCRIPTION_EXTRACTS_FILE = "snoinc_data_extracts/loinc_codes_with_part_descriptions.csv"
OUTPUT_SENTENCES_FILE = "training_data_files/part_description_sentences.txt"


def create_tsdae_data(nlp: spacy.language.Language, parts_fp: str, out_fp: str) -> None:
    """
    Constructs a collection of domain-adapted sentences fit for use with
    unsupervised TSDAE (Transformer-based Sentence-Denoising Auto-Encoder)
    pre-training. Applies a variety of preprocessing, formatting, and
    cleaning operations to ensure that the resulting sentences are high-
    quality and free of artifacts (e.g. URLs, bracketed referential text,
    extraneous characters and spacing, etc.).

    :param nlp: An instantiated Spacy model, preferably one of the English
      core web models (e.g. "en-core-web-sm")
    :param parts_fp: A string path to a file containing comma-separated
      LOINC codes and their corresponding part descriptions.
    :param out_fp: A string path at which to write the sentences file.
    :returns: None
    """
    # Many extracted parts contain duplicate passages (e.g. for
    # organism tests in different modalities). Only store one copy
    # of each to increase sentential diversity.
    descriptions = set()

    # Some descriptions are built up over multiple lines due to
    # carriage returns within descriptions. All new descriptions
    # start with a LOINC code line, which is a hyphenated number.
    curr_description = ""

    with open(parts_fp, "r") as fp:
        for loinc_line in fp:
            stripped_loinc_line = loinc_line.strip()
            if stripped_loinc_line != "":
                if _line_starts_with_loinc_code(stripped_loinc_line):
                    # Can fully process a description when we know we've hit a new
                    # LOINC code and have all the text for the previous code
                    if curr_description != "":
                        curr_description = _preprocess_part_description(curr_description)
                        if curr_description != "":
                            descriptions.add(curr_description)
                        curr_description = ""

                curr_description += stripped_loinc_line + " "

        # Might have residual data in the current tracker, process it
        if curr_description != "":
            curr_description = _preprocess_part_description(curr_description)
            descriptions.add(curr_description)

    # Now apply sentential parsing from spacy to get the final sentences
    processed_docs = nlp.pipe(list(descriptions))

    # Write the output sentence by sentence from the spacy parser
    with open(out_fp, "w") as fp:
        for doc in processed_docs:
            for sent in doc.sents:
                st = sent.text.strip()
                st = _post_process_sentence(st)
                if st != "":
                    fp.write(st + "\n")


def _line_is_citation(line: str) -> bool:
    """
    Helper method to determine if a given line of string text is an academic
    or institutional citation. A line is deemed a citation if it includes
    a text group of the form

      "[YYYY] [MMM][optional: DD];publication_num(periodical_num):page-page

    OR of the abbreviated form

      [YYYY]; periodical_number(sub_number):startpage-endpage

    since these are the publication citation formats for APA.
    """
    format_1 = re.search(r"\d{4} [A-Za-z]{3}(\s\d+)?;\d+\(\d+\):\d+-\d+\.", line)
    format_2 = re.search(r"\d{4};\s?\d*(\(\d+\))?:\d*-\d*", line)
    return format_1 or format_2


def _line_starts_with_loinc_code(line: str) -> Union[re.Match, None]:
    """
    Helper method to determine if a line of string text begins with a
    numerically formatted LOINC code (defined as a number of one or more
    digits, followed by a dash, and then one digit). LOINC codes that
    represent new description entries are also followed by a comma, rather
    than whitespace, which signifies they are part of another description.
    """
    # Note we want to use match here, not search, because match anchors
    # the expression to the beginning of the string only
    return re.match(r"^\d+-\d,", line)


def _preprocess_part_description(loinc_line: str) -> str:
    """
    Helper function to process a fully compiled passage from a Part Description.
    Whitespaces are standardized and handled, the LOINC numeric code proper is
    split off, and any extraneous character formatting around e.g. punctuation
    or details within the description are collapsed to a single string line.
    """
    # The description itself might have commas as regular sentence syntax,
    # we only want the first comma that signifies the LOINC code
    _, d = loinc_line.split(",", maxsplit=1)

    # Some lines are academic citations; delete those entirely
    if _line_is_citation(d):
        return ""

    # Most quotation marks in the LOINC extracts are doubled for no
    # reason, compress them for downstream processing
    d = re.sub(r'""', '"', d.strip())

    # Some lines start and end with quotes, get rid of those
    # but leave others in case they're semantically meaningful
    if d[0] == '"' or d[0] == "“":
        d = d[1:]
    if d[-1] == '"' or d[-1] == "”":
        d = d[:-1]

    # LOINC is full of citation or referential data in the form of bracketed
    # text, parenthetical EC references to organisms, and embedded URLs.
    # We don't want any of that in our sentence examples.
    d = re.sub(r"\[(?<=\[)[^\]]*?(?=\])\]", "", d.strip())
    d = re.sub(r"[\(\[\{]\s*[Hh]ttps?:(\/\/)?.+\s*[\)\]\}]", "", d.strip())
    d = re.sub(r"PMID:\s\d+", "", d.strip())
    d = re.sub(r"\(?EC\s\d+\.\d+\.\d+\.\d+\)?", "", d.strip())
    d = re.sub(r"RefID\s\d{5}", "", d.strip())
    d = re.sub(r"NCBI\sBookself\s?,\s\d{4}", "", d.strip())

    # Some sentences are formatted internally with multiple sequential
    # whitespaces / tabs, compress those to one space
    d = re.sub(r"\s+", " ", d.strip())

    # Some sentences have odd spacing around punctuation marks (e.g.
    # ' , ' or ' ( '). Clean those up.
    d = re.sub(r"\s,\s", ", ", d.strip())
    d = re.sub(r"\s\.\s", ". ", d.strip())
    d = re.sub(r"\s\(\s", " (", d.strip())
    d = re.sub(r"\s\)\s", ") ", d.strip())

    return d


def _post_process_sentence(st: str) -> str:
    """
    Helper function that applies post-processing cleanups to the result
    of Spacy's sentence tokenizer. Some artifacts can't be caught in the
    initial document compilation (where they could be split across lines
    or have other formatting in the way) so this post-check ensures that
    only high quality sentences make it into the training file.
    """
    # Some lines still end in quotes and spaces
    st = re.sub(r'\s*"\s*$', "", st)
    # If a line has an "accessed YEAR" formatting after sentence
    # splitting, it's a website or textbook citation
    if re.search(r"[Aa]ccessed \d{4}", st.strip()):
        return ""
    # Some initial data had a meaningful sentence followed by a
    # citation; those got split off as their own sentences, so
    # we can catch them here
    if re.search(r"\d{4};\s\d*:\d*-\d*", st.strip()) or re.search(
        r"(\d{4})?,?[;\s]\d+:\d+\s?-\s?\d+(?!:)\.?", st.strip()
    ):
        return ""
    # Sentences with non-bracketed URLs tend to use them as pointers
    # for non-clinically significant data, such as "More information
    # can be found at http://xxxx". We lose only 4 sentences from the
    # dataset by eliminating them, but we filter >100 bad structures.
    if re.search(r"(?<!\()[Hh]ttps?:\/\/.+", st.strip()):
        return ""
    # The above replacements can leave some kruft periods and commas,
    # clean those up
    if st == "." or st == ",":
        return ""
    # Finally, if the whole "sentence" is either one misplaced word
    # or too short to have clinical context, ditch it
    if len(st.strip().split()) < 4:
        return ""

    return st


if __name__ == "__main__":
    nlp: spacy.language.Language = spacy.load("en_core_web_sm")
    create_tsdae_data(nlp, PART_DESCRIPTION_EXTRACTS_FILE, OUTPUT_SENTENCES_FILE)
