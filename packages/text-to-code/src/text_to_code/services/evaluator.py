from collections.abc import Sequence

from pydantic import Field

from text_to_code.models.evaluator import BaseEvaluationCriteria
from text_to_code.models.evaluator import CodeSystemValues
from text_to_code.models.evaluator import CodeTranslation
from text_to_code.models.evaluator import TranslationPreference
from text_to_code.models.evaluator import TranslationSelectionStrategy
from text_to_code.models.evaluator import XPathPriority
from text_to_code.services import utils

from ..models.eicr import Candidate
from ..models.eicr import DataField
from ..models.eicr import LabXPaths


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
    if system is None:
        return None

    if system in preference.loinc_system_values:
        return CodeTranslation.LOINC

    if system in preference.snomed_system_values:
        return CodeTranslation.SNOMED

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
        if _classify_translation_system(c, preference) == CodeTranslation.LOINC:
            return c

    for c in translation_candidates:
        if _classify_translation_system(c, preference) == CodeTranslation.SNOMED:
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
    for priority in criteria.ordered_priorities():
        best = _resolve_best_for_xpath(
            candidates=candidates,
            xpath=priority.xpath,
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
            loinc_system_values=CodeSystemValues.LOINC_VALUES,
            snomed_system_values=CodeSystemValues.SNOMED_VALUES,
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


def _meets_word_count(text: str, word_count: int) -> bool:
    """Verify if the number of words within a given text string meets the word count rule supplied.

    :param text: The text string being evaluated.
    :param word_count: The number of words required for
        a given data field, based upon the configured rule.
    :returns: A boolean (True or False) if the text meets the
        word count rule criteria or not.
    """
    return len(text.split()) > word_count


def is_text_viable(data_field: DataField, text: str) -> bool:
    """Verify a text string is viable for evaluation for a specified data field, i.e. 'Lab Result'.

    :param data_field: The data field, from an eICR, that
        is being evaluated within the TTC module.
    :param text: The text string being evaluated, for a given
        data_field, to see if it's viable for evaluation in
        the TTC module based upon data_field specific rules.
    :returns: A boolean if the text for a data_field is viable for TTC or not.
    """
    # Get the config for the specified data field
    data_field_config = utils.get_config_for_data_field(data_field)

    # Check if there is a word count rule defined for this data field
    if data_field_config.min_word_count:
        return _meets_word_count(text, data_field_config.min_word_count)

    return True
