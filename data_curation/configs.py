import schemas.augmentation as schemas

"""
A configuration meant for generating a validation data set in which each base
LOINC code has a single, highly processed text example associated with it.
Enhancement is *always* performed to inject semantic variance and deviation,
and additional operations are used to fine-tune data scrambling so that 
models can't learn just word order but have to use meaning instead.
This config works on the LLM theory that it is better to have a single,
extremely high-quality representative of an output class than it is to have
multiple low-grade variations of noise.
"""
ONE_SHOT_VALIDATION_AUGMENTATION: schemas.AugmentationConfig = {
    "enhancement_all": {"min_enhances": 1, "max_enhances": 4, "enhancement_prob": 1.0},
    "insertion": {
        "min_inserts": 1,
        "max_inserts": 2,
        "insert_prob_after_enhance": 0.5,
    },
    "permutation": {"min_swaps": 1, "max_swaps": 3, "swap_prob": 0.5},
    "deletion": {
        "deletion_mode": "char",
        "min_deletes": 1,
        "max_deletes": 8,
        "max_deletes_per_word": 2,
        "deletion_prob": 0.5,
    },
}

"""
A default augmentation configuration meant as a "representative" synthetic
baseline for most cases. Slightly favors applying enhancement, but if 
enhancement isn't performed, heavily skews towards insertion. This promotes 
variance in semantic meaning in the input, which then undergoes a moderate
level of skewing / corruption.
"""
DEFAULT_AUGMENTATION: schemas.AugmentationConfig = {
    "enhancement_all": {"min_enhances": 1, "max_enhances": 4, "enhancement_prob": 0.6},
    "insertion": {
        "min_inserts": 1,
        "max_inserts": 3,
        "insert_prob_after_enhance": 0.3,
        "insert_prob_without_enhance": 0.7,
    },
    "permutation": {"min_swaps": 1, "max_swaps": 3, "swap_prob": 0.3},
    "deletion": {
        "deletion_mode": "char",
        "min_deletes": 1,
        "max_deletes": 6,
        "max_deletes_per_word": 2,
        "deletion_prob": 0.4,
    },
}


"""
An augmentation configuration meant for cases in which applying enhancement
is undesirable or enhancement data is too sparse. Insertions are all but
guaranteed with this configuration as a means to encourage semantic and
syntactic variety. Since insertion is index-random, permutation swaps are
less important than might otherwise seem, but sporadic deletion becomes
more important to break up character-cluster memoization.
"""
AUGMENTATION_WITHOUT_ENHANCEMENT: schemas.AugmentationConfig = {
    "insertion": {"min_inserts": 1, "max_inserts": 3, "insert_prob_without_enhance": 1.0},
    "permutation": {"min_swaps": 1, "max_swaps": 3, "swap_prob": 0.3},
    "deletion": {
        "deletion_mode": "char",
        "min_deletes": 1,
        "max_deletes": 8,
        "max_deletes_per_word": 2,
        "deletion_prob": 0.6,
    },
}


"""
A configuration intended for granular control over the levels of enhancement
and semantic variance performed. This config is a good candidate for simulating
higher levels of "human shorthand" by preferencing synthetic data towards
syntactic rather than semantic substitution. Deletion is down-weighted here
to not interfere with synonym and abbreviation usage.
"""
AUGMENTATION_INDIVIDUALLY_SPECIFIED: schemas.AugmentationConfig = {
    "enhancement_abbreviation": {"min_enhances": 1, "max_enhances": 3, "enhancement_prob": 0.8},
    "enhancement_synonyms": {"min_enhances": 1, "max_enhances": 2, "enhancement_prob": 0.4},
    "insertion": {
        "min_inserts": 1,
        "max_inserts": 2,
        "insert_prob_after_enhance": 0.4,
        "insert_prob_without_enhance": 0.8,
    },
    "permutation": {"min_swaps": 1, "max_swaps": 3, "swap_prob": 0.4},
    "deletion": {
        "deletion_mode": "word",
        "min_deletes": 1,
        "max_deletes": 5,
        "max_deletes_per_word": 1,
        "deletion_prob": 0.2,
    },
}

"""
A configuration intended for the generation of augmented LOINC files, with
granular control over the levels of enhancement at the individual type level. 
"""
LOINC_FILE_GENERATION_AUGMENTATION: schemas.LoincFileGenerationConfig = {
    "long_common_name": DEFAULT_AUGMENTATION,
    "short_name": DEFAULT_AUGMENTATION,
    "display_name": DEFAULT_AUGMENTATION,
}
