from __future__ import annotations

from collections.abc import Sequence
from enum import StrEnum

from pydantic import BaseModel
from pydantic import Field

from text_to_code.services.evaluator import is_text_viable

from .eicr import Candidate
from .eicr import DataField
from .eicr import LabXPaths


class TranslationSystem(StrEnum):
    """Logical classification of known code systems used to prioritize translation candidates.

    This enum is not derived from raw XML directly. Instead, it is inferred by comparing a
    Candidate.system value against configured system URI lists.

    :returns: A TranslationSystem enum value when the candidate system matches a configured
        code system list, otherwise None.
    """

    LOINC = "LOINC"
    SNOMED = "SNOMED"


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


def _classify_translation_system(
    candidate: Candidate,
    preference: TranslationPreference,
) -> TranslationSystem | None:
    """Classify a translation candidate as LOINC or SNOMED based on its Candidate.system value.

    :param candidate: A Candidate extracted from a translation XPath.
    :param preference: Translation system preference configuration.
    :returns: The classified TranslationSystem value if Candidate.system matches a configured
        system identifier, otherwise None.
    """
    system = candidate.system
    if system is None:
        return None

    if system in preference.loinc_system_values:
        return TranslationSystem.LOINC

    if system in preference.snomed_system_values:
        return TranslationSystem.SNOMED

    return None


def _select_translation_candidate(
    translation_candidates: Sequence[Candidate],
    preference: TranslationPreference,
) -> Candidate | None:
    """Select the best translation candidate according to configured preferences.

    :param translation_candidates: Candidates extracted from a translation XPath.
    :param preference: Translation system preference configuration.
    :returns: The selected Candidate, or None if no candidates are available.
    """
    if not translation_candidates:
        return None

    if preference.strategy == TranslationSelectionStrategy.FIRST:
        return translation_candidates[0]

    any_has_system = any(c.system is not None for c in translation_candidates)
    if not any_has_system:
        return translation_candidates[0]

    for c in translation_candidates:
        if _classify_translation_system(c, preference) == TranslationSystem.LOINC:
            return c

    for c in translation_candidates:
        if _classify_translation_system(c, preference) == TranslationSystem.SNOMED:
            return c

    return translation_candidates[0]


def _resolve_best_for_xpath(
    candidates: Sequence[Candidate],
    xpath: LabXPaths,
    preference: TranslationPreference,
) -> Candidate | None:
    """Resolve the best candidate for a given XPath.

    Translation XPaths may produce multiple candidates and require additional selection logic.
    Non-translation XPaths return the first matching candidate.

    :param candidates: All Candidate entries extracted for the current observation/error.
    :param xpath: The LabXPaths source to resolve.
    :param preference: Translation selection preferences used for translation XPaths.
    :returns: The resolved Candidate for the XPath, or None if no candidate is available.
    """
    matches = [c for c in candidates if c.xpath == xpath]
    if not matches:
        return None

    if xpath in {
        LabXPaths.CODE_TRANSLATION_DISPLAY_NAME,
        LabXPaths.CODE_TRANSLATION_ORIGINAL_TEXT,
    }:
        return _select_translation_candidate(matches, preference)

    return matches[0]


def select_relevant_text(
    *,
    candidates: Sequence[Candidate],
    criteria: BaseEvaluationCriteria,
) -> str | None:
    """Select the single most relevant viable text string from a list of candidates.

    Evaluation proceeds in priority order:
    - For each prioritized XPath, resolve the best candidate for that XPath.
    - Validate viability via dibbs_text_to_code.services.evaluator.is_text_viable.
    - Return the first viable candidate value.

    :param candidates: All Candidate entries extracted for the current observation/error.
    :param criteria: The evaluation criteria defining priority order and translation behavior.
    :returns: The selected text string to submit to OpenSearch, or None if no candidate is viable.
    """
    for prio in criteria.ordered_priorities():
        best = _resolve_best_for_xpath(
            candidates=candidates,
            xpath=prio.xpath,
            preference=criteria.translation_preference,
        )
        if best is None:
            continue

        chosen = best.value.strip()
        if not chosen:
            continue

        if criteria.data_field is not None and not is_text_viable(criteria.data_field, chosen):
            continue

        return chosen

    return None


class LabTestNameOrderedEvaluationCriteria(BaseEvaluationCriteria):
    """Evaluation criteria for selecting text relevant to Lab Test Name Ordered.

    This config encodes the memo priority order:
    1) code/displayName
    2) translation/displayName
    3) code/originalText
    4) translation/originalText
    """

    data_field: DataField = DataField.LAB_TEST_NAME_ORDERED

    priorities: list[XPathPriority] = Field(
        default_factory=lambda: [
            XPathPriority(xpath=LabXPaths.CODE_DISPLAY_NAME, priority=1),
            XPathPriority(xpath=LabXPaths.CODE_TRANSLATION_DISPLAY_NAME, priority=2),
            XPathPriority(xpath=LabXPaths.CODE_ORIGINAL_TEXT, priority=3),
            XPathPriority(xpath=LabXPaths.CODE_TRANSLATION_ORIGINAL_TEXT, priority=4),
        ]
    )

    translation_preference: TranslationPreference = Field(
        default_factory=lambda: TranslationPreference(
            strategy=TranslationSelectionStrategy.PREFER_SYSTEM_ORDER,
            loinc_system_values=[
                "http://loinc.org",
                "urn:oid:2.16.840.1.113883.6.1",
            ],
            snomed_system_values=[
                "http://snomed.info/sct",
                "urn:oid:2.16.840.1.113883.6.96",
            ],
        )
    )


class LabTestNameResultedEvaluationCriteria(BaseEvaluationCriteria):
    """Evaluation criteria for selecting text relevant to Lab Test Name Resulted.

    This config encodes the memo priority order:
    1) code/displayName
    2) translation/displayName
    3) code/originalText
    4) translation/originalText
    """

    data_field: DataField = DataField.LAB_TEST_NAME_RESULTED

    priorities: list[XPathPriority] = Field(
        default_factory=lambda: [
            XPathPriority(xpath=LabXPaths.CODE_DISPLAY_NAME, priority=1),
            XPathPriority(xpath=LabXPaths.CODE_TRANSLATION_DISPLAY_NAME, priority=2),
            XPathPriority(xpath=LabXPaths.CODE_ORIGINAL_TEXT, priority=3),
            XPathPriority(xpath=LabXPaths.CODE_TRANSLATION_ORIGINAL_TEXT, priority=4),
        ]
    )

    translation_preference: TranslationPreference = Field(
        default_factory=lambda: TranslationPreference(
            strategy=TranslationSelectionStrategy.PREFER_SYSTEM_ORDER,
            loinc_system_values=[
                "http://loinc.org",
                "urn:oid:2.16.840.1.113883.6.1",
            ],
            snomed_system_values=[
                "http://snomed.info/sct",
                "urn:oid:2.16.840.1.113883.6.96",
            ],
        )
    )


EvaluationConfigType = type[BaseEvaluationCriteria]


EVALUATION_REGISTRY: dict[DataField, EvaluationConfigType] = {
    DataField.LAB_TEST_NAME_ORDERED: LabTestNameOrderedEvaluationCriteria,
    DataField.LAB_TEST_NAME_RESULTED: LabTestNameResultedEvaluationCriteria,
}


def get_evaluation_criteria_for_data_field(data_field: DataField) -> BaseEvaluationCriteria:
    """Retrieve a fresh evaluation criteria instance for the specified DataField.

    :param data_field: The data field being evaluated within the TTC module.
    :returns: A new evaluation criteria instance for the specified DataField.
    """
    try:
        cls = EVALUATION_REGISTRY[data_field]
    except KeyError as e:
        raise KeyError(f"No evaluation criteria registered for DataField {data_field}") from e

    return cls()
