from enum import StrEnum
from typing import ClassVar

from pydantic import BaseModel
from pydantic import Field

from ..models.eicr import DataField
from ..models.eicr import LabXPaths


class CodeTranslation(StrEnum):
    """Logical classification of known code systems used to prioritize translation candidates.

    This enum is not derived from raw XML directly. Instead, it is inferred by comparing a
    Candidate.system value against configured system URI lists.

    :returns: A CodeTranslation enum value when the candidate system matches a configured
        code system list, otherwise None.
    """

    LOINC = "LOINC"
    SNOMED = "SNOMED"


class CodeSystemValues(list[str]):
    """A list of code system identifier strings used to classify translation candidates."""

    LOINC_VALUES: ClassVar[list[str]] = [
        "http://loinc.org",
        "urn:oid:2.16.840.1.113883.6.1",
    ]

    SNOMED_VALUES: ClassVar[list[str]] = [
        "http://snomed.info/sct",
        "urn:oid:2.16.840.1.113883.6.96",
    ]


class TranslationSelectionStrategy(StrEnum):
    """Strategy for selecting one translation candidate when multiple are available.

    FIRST:
        Always return the first translation candidate encountered.

    PREFER_SYSTEM_ORDER:
        If any translation has system information, prefer:
        1) LOINC
        2) SNOMED
        3) otherwise, the first translation
    """

    FIRST = "first"
    PREFER_SYSTEM_ORDER = "prefer_system_order"


class FieldRules(BaseModel):
    """Validation rule container for evaluation criteria.

    This model exists to support data-field specific rules at the evaluation-criteria layer.
    Current viability checks should use dibbs_text_to_code.services.evaluator.is_text_viable
    to ensure TTC rule logic stays centralized.

    :param min_word_count: Optional minimum word count rule for candidate viability.
    """

    min_word_count: int | None = Field(
        default=None,
        ge=0,
        description="Optional minimum number of words required for candidate text to be valid.",
    )


class TranslationPreference(BaseModel):
    """Preferences for choosing among multiple translations when a system attribute is available.

    :param strategy: Strategy used when selecting among multiple translation candidates.
    :param loinc_system_values: System identifiers that should be treated as LOINC.
    :param snomed_system_values: System identifiers that should be treated as SNOMED.
    """

    strategy: TranslationSelectionStrategy = TranslationSelectionStrategy.PREFER_SYSTEM_ORDER
    loinc_system_values: list[str] = Field(
        default_factory=list,
        description="System identifiers that should be treated as LOINC.",
    )
    snomed_system_values: list[str] = Field(
        default_factory=list,
        description="System identifiers that should be treated as SNOMED.",
    )


class XPathPriority(BaseModel):
    """A single prioritized source of candidate text.

    :param xpath: The LabXPaths entry identifying where the candidate text was extracted from.
    :param priority: Numeric priority where 1 is highest priority.
    :param rules: Optional rule overrides applied only for this specific XPath source.
    """

    xpath: LabXPaths
    priority: int = Field(..., ge=1)
    rules: FieldRules | None = None


class BaseEvaluationCriteria(BaseModel):
    """Base configuration for selecting the most relevant text for a given DataField.

    :param data_field: The DataField this evaluation criteria applies to.
    :param priorities: Prioritized XPath sources considered during evaluation.
    :param rules: Optional rules applied to candidates during evaluation.
    :param translation_preference: Preferences for selecting among translation candidates.
    """

    data_field: DataField | None = Field(
        default=None,
        description="The DataField this evaluation criteria applies to.",
    )
    priorities: list[XPathPriority] = Field(
        default_factory=list,
        description="Prioritized XPath sources considered during evaluation.",
    )
    rules: FieldRules | None = Field(
        default=None,
        description="Optional rules applied to candidates during evaluation.",
    )
    translation_preference: TranslationPreference = Field(
        default_factory=TranslationPreference,
        description="Preferences used when selecting among translation candidates.",
    )

    def ordered_priorities(self) -> list[XPathPriority]:
        """Return candidate priorities sorted from highest to lowest importance.

        :returns: A list of XPathPriority entries sorted by ascending priority value.
        """
        return sorted(self.priorities, key=lambda p: p.priority)
