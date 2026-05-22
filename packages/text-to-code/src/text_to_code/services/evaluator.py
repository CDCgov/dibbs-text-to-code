from shared_models import DataField
from text_to_code.models.evaluator import (
    EVALUATION_REGISTRY,
    BaseEvaluationCriteria,
    CodeTranslation,
    TranslationPreference,
    TranslationSelectionStrategy,
)

from ..models.eicr import Candidate, LabXPaths


def _classify_translation_system(
    candidate: Candidate,
    preference: TranslationPreference,
) -> CodeTranslation | None:
    """Classify a translation candidate as LOINC or SNOMED based on its Candidate.system value.

    :param candidate: A Candidate extracted from a translation XPath.
    :param preference: Translation system preference configuration.
    :returns: The classified CodeTranslation value if Candidate.system matches a configured
        system identifier, otherwise None.
    """
    system = candidate.system

    if system in preference.loinc_system_values:
        return CodeTranslation.LOINC

    if system in preference.snomed_system_values:
        return CodeTranslation.SNOMED

    return None


def _select_translation_candidate(
    translation_candidates: list[Candidate],
    preference: TranslationPreference,
) -> Candidate | None:
    """Select the best translation candidate according to configured preferences.

    :param translation_candidates: Candidates extracted from a translation XPath.
    :param preference: Translation system preference configuration.
    :returns: The selected Candidate, or None if no candidates are available.
    """
    if preference.strategy == TranslationSelectionStrategy.FIRST:
        return translation_candidates[0]

    any_has_system = any(c.system is not None for c in translation_candidates)
    if not any_has_system:
        return translation_candidates[0]

    for c in translation_candidates:
        if _classify_translation_system(c, preference) == CodeTranslation.LOINC:
            return c

    for c in translation_candidates:
        if _classify_translation_system(c, preference) == CodeTranslation.SNOMED:
            return c

    return translation_candidates[0]


def _resolve_best_for_xpath(
    candidates: list[Candidate],
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


def select_relevant_text(candidates: list[Candidate], field_type: DataField) -> Candidate | None:
    """Select the single most relevant viable text string from a list of candidates.

    Evaluation proceeds in priority order:
    - For each prioritized XPath, resolve the best candidate for that XPath.
    - Return the first viable candidate value.

    :param candidates: All Candidate entries extracted for the current observation/error.
    :param criteria: The evaluation criteria defining priority order and translation behavior.
    :returns: The selected Candidate, or None if no candidate is viable.
    """
    criteria = _get_evaluation_criteria_for_data_field(field_type)
    for priority in criteria.ordered_priorities():
        best_candidate = _resolve_best_for_xpath(
            candidates=candidates,
            xpath=priority.xpath,
            preference=criteria.translation_preference,
        )
        if best_candidate is None:
            continue

        if not best_candidate.value.strip():
            continue

        return best_candidate

    return None


def _get_evaluation_criteria_for_data_field(data_field: DataField) -> BaseEvaluationCriteria:
    """Retrieve a fresh evaluation criteria instance for the specified DataField.

    :param data_field: The data field being evaluated within the TTC module.
    :returns: A new evaluation criteria instance for the specified DataField.
    """
    try:
        cls = EVALUATION_REGISTRY[data_field]
    except KeyError as e:
        raise KeyError(f"No evaluation criteria registered for DataField {data_field}") from e

    return cls()
