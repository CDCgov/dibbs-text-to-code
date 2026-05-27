"""data_curation.schemas.enhancement_type."""

import enum


class EnhancementType(enum.StrEnum):
    """A simple schema for defining the type of LOINC enhancement available during synthetic data generation."""

    ABBRV = "abbrv"
    SYNONYMS = "synonyms"
    ALL = "all"
