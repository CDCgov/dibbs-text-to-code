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
        "x_paths": ["some path", "some other path"],  # store the X-Paths in order of importance
    },
    "lab_result": {
        "text_word_count": 2,  # anything that is greater than 2
        # putting x_paths here for now, but we may not need/want this
        "x_paths": ["some path", "some other path"],  # store the X-Paths in order of importance
    },
    "lab_value": {},
    "lab_interp": {},
}

MODEL_NAME = "Qwen/Qwen3-Embedding-8B"
