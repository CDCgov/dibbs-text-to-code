import data_curation.schemas.augmentation as schemas

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
