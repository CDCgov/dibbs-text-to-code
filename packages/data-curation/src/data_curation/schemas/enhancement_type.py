"""data_curation.schemas.enhancement_type.
~~~~~~~~~~~~~~~~~~~~~~~~~

A simple schema for defining the type of LOINC enhancement available
during synthetic data generation.
"""

import enum


class EnhancementType(enum.StrEnum):
    ABBRV = "abbrv"
    SYNONYMS = "synonyms"
    ALL = "all"
