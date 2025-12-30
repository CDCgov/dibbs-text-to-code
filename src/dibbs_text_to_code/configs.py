# Store a list of all the data fields/elements that are relevant
# This may not be maintainable - but for our purposes should suffice
# for now
DATA_FIELDS = ["lab_order", "lab_result", "lab_value", "lab_interp"]

# Putting this here for now to store rules for
# evaluating text, for specified data elements,
# to see if they are viable for TTC
# TODO: Does this work for us or is there something better?
DATA_FIELD_TEXT_RULES = {
    "lab_order": {
        "text_word_count": 2,  # anything that is greater than 2
        # putting x_paths here for now, but we may not need/want this
        "x_paths": [
            "/code/@displayName",
            "/code/originalText/text()",
            "/code/translation/@displayName",
            "/code/translation/originalText/text()",
            "/code/translation/text/text()",
        ],
    },
    "lab_result": {
        "text_word_count": 2,  # anything that is greater than 2
        # putting x_paths here for now, but we may not need/want this
        "x_paths": [
            "/code/@displayName",
            "/code/originalText/text()",
            "/code/text/text()",
            "/code/translation/@displayName",
            "/code/translation/originalText/text()",
            "/code/translation/text/text()",
        ],
    },
    "lab_value": {},
    "lab_interp": {},
}

# TODO: using examples provided by APHL - may need to confirm!
SCHEMATRON_ERRORS = {
    "lab_order": [
        "Text to Code: Lab Test Name Ordered does not have a @code attribute",
        "Text to Code: Lab Test Name Ordered code and translation data elements @codeSystem attribute are not LOINC 2.16.840.1.113883.6.1",
    ],
    "lab_result": [
        "Text to Code: Lab Test Name Resulted does not have a @code attribute",
        "Text to Code: Lab Test Name Resulted code and translation data elements @codeSystem attribute are not LOINC 2.16.840.1.113883.6.1",
    ],
}

MODEL_NAME = "Snowflake/snowflake-arctic-embed-m"
# smaller model to get tests to run faster and with less memor "all-MiniLM-L6-v2" -- size 384
# TOO BIG TO RUN TESTS against ----  "Qwen/Qwen3-Embedding-8B"
