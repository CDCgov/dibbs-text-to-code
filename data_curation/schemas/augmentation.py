"""
data_curation.schemas.augmentation
~~~~~~~~~~~~~~~~~~~~~~~~~

This module contains the schema definitions for the augmented data.
"""

import enum


class EnhancementType(str, enum.Enum):
    ABBRV = "abbrv"
    SYNONYMS = "synonyms"
    ALL = "all"
