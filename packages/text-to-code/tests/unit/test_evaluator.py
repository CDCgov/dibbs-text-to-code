import pytest

from shared_models import DataField
from text_to_code.models.eicr import Candidate
from text_to_code.models.eicr import LabXPaths
from text_to_code.models.evaluator import TranslationPreference
from text_to_code.models.evaluator import TranslationSelectionStrategy
from text_to_code.services import evaluator
from text_to_code.services.evaluator import get_evaluation_criteria_for_data_field
from text_to_code.services.evaluator import select_relevant_text


def test_classify_translation_system_returns_none_when_system_is_none() -> None:
    candidate = Candidate(
        xpath=LabXPaths.CODE_TRANSLATION_DISPLAY_NAME,
        value="translation text",
        system=None,
    )

    preference = get_evaluation_criteria_for_data_field(
        DataField.LAB_TEST_NAME_RESULTED
    ).translation_preference

    selected = evaluator._classify_translation_system(candidate, preference)

    assert selected is None


def test_classify_translation_system_returns_loinc() -> None:
    candidate = Candidate(
        xpath=LabXPaths.CODE_TRANSLATION_DISPLAY_NAME,
        value="Preferred LOINC text",
        system="http://loinc.org",
    )

    preference = get_evaluation_criteria_for_data_field(
        DataField.LAB_TEST_NAME_RESULTED
    ).translation_preference

    selected = evaluator._classify_translation_system(candidate, preference)

    assert selected is not None
    assert selected.value == "LOINC"


def test_classify_translation_system_returns_snomed() -> None:
    candidate = Candidate(
        xpath=LabXPaths.CODE_TRANSLATION_DISPLAY_NAME,
        value="Preferred SNOMED text",
        system="http://snomed.info/sct",
    )

    preference = get_evaluation_criteria_for_data_field(
        DataField.LAB_TEST_NAME_RESULTED
    ).translation_preference

    selected = evaluator._classify_translation_system(candidate, preference)

    assert selected is not None
    assert selected.value == "SNOMED"


def test_classify_translation_system_returns_none_when_system_is_unrecognized() -> None:
    candidate = Candidate(
        xpath=LabXPaths.CODE_TRANSLATION_DISPLAY_NAME,
        value="Other translation text",
        system="urn:oid:9.9.9.9.9",
    )

    preference = get_evaluation_criteria_for_data_field(
        DataField.LAB_TEST_NAME_RESULTED
    ).translation_preference

    selected = evaluator._classify_translation_system(candidate, preference)

    assert selected is None


def test_select_translation_candidate_returns_none_when_translation_candidates_are_empty() -> None:
    preference = get_evaluation_criteria_for_data_field(
        DataField.LAB_TEST_NAME_RESULTED
    ).translation_preference

    selected = evaluator._select_translation_candidate([], preference)

    assert selected is None


def test_select_translation_candidate_returns_first_when_strategy_is_first() -> None:
    candidates = [
        Candidate(
            xpath=LabXPaths.CODE_TRANSLATION_DISPLAY_NAME,
            value="first translation",
            system="urn:oid:1.2.3",
        ),
        Candidate(
            xpath=LabXPaths.CODE_TRANSLATION_DISPLAY_NAME,
            value="second translation",
            system="http://loinc.org",
        ),
    ]

    preference = TranslationPreference(
        strategy=TranslationSelectionStrategy.FIRST,
        loinc_system_values=["http://loinc.org"],
        snomed_system_values=["http://snomed.info/sct"],
    )

    selected = evaluator._select_translation_candidate(candidates, preference)

    assert selected == candidates[0]


def test_select_translation_candidate_returns_first_when_no_candidate_has_system() -> None:
    candidates = [
        Candidate(
            xpath=LabXPaths.CODE_TRANSLATION_DISPLAY_NAME,
            value="first translation",
            system=None,
        ),
        Candidate(
            xpath=LabXPaths.CODE_TRANSLATION_DISPLAY_NAME,
            value="second translation",
            system=None,
        ),
    ]

    preference = get_evaluation_criteria_for_data_field(
        DataField.LAB_TEST_NAME_RESULTED
    ).translation_preference

    selected = evaluator._select_translation_candidate(candidates, preference)

    assert selected == candidates[0]


def test_select_translation_candidate_returns_snomed_when_no_loinc_match_exists() -> None:
    candidates = [
        Candidate(
            xpath=LabXPaths.CODE_TRANSLATION_DISPLAY_NAME,
            value="unknown translation",
            system="urn:oid:1.2.3",
        ),
        Candidate(
            xpath=LabXPaths.CODE_TRANSLATION_DISPLAY_NAME,
            value="preferred snomed translation",
            system="http://snomed.info/sct",
        ),
    ]

    preference = get_evaluation_criteria_for_data_field(
        DataField.LAB_TEST_NAME_RESULTED
    ).translation_preference

    selected = evaluator._select_translation_candidate(candidates, preference)

    assert selected == candidates[1]


def test_select_translation_candidate_returns_first_when_systems_exist_but_none_match_preference() -> (
    None
):
    candidates = [
        Candidate(
            xpath=LabXPaths.CODE_TRANSLATION_DISPLAY_NAME,
            value="first translation",
            system="urn:oid:1.2.3",
        ),
        Candidate(
            xpath=LabXPaths.CODE_TRANSLATION_DISPLAY_NAME,
            value="second translation",
            system="urn:oid:4.5.6",
        ),
    ]

    preference = get_evaluation_criteria_for_data_field(
        DataField.LAB_TEST_NAME_RESULTED
    ).translation_preference

    selected = evaluator._select_translation_candidate(candidates, preference)

    assert selected == candidates[0]


def test_resolve_best_for_xpath_returns_none_when_no_matches_exist() -> None:
    candidates = [
        Candidate(
            xpath=LabXPaths.CODE_DISPLAY_NAME,
            value="display name",
            system=None,
        ),
    ]

    preference = get_evaluation_criteria_for_data_field(
        DataField.LAB_TEST_NAME_RESULTED
    ).translation_preference

    selected = evaluator._resolve_best_for_xpath(
        candidates=candidates,
        xpath=LabXPaths.CODE_ORIGINAL_TEXT,
        preference=preference,
    )

    assert selected is None


def test_resolve_best_for_xpath_returns_first_match_for_non_translation_xpath() -> None:
    candidates = [
        Candidate(
            xpath=LabXPaths.CODE_DISPLAY_NAME,
            value="first display",
            system=None,
        ),
        Candidate(
            xpath=LabXPaths.CODE_DISPLAY_NAME,
            value="second display",
            system=None,
        ),
    ]

    preference = get_evaluation_criteria_for_data_field(
        DataField.LAB_TEST_NAME_RESULTED
    ).translation_preference

    selected = evaluator._resolve_best_for_xpath(
        candidates=candidates,
        xpath=LabXPaths.CODE_DISPLAY_NAME,
        preference=preference,
    )

    assert selected == candidates[0]


def test_resolve_best_for_xpath_prefers_loinc_for_translation_xpath() -> None:
    candidates = [
        Candidate(
            xpath=LabXPaths.CODE_TRANSLATION_DISPLAY_NAME,
            value="SNOMED translation",
            system="http://snomed.info/sct",
        ),
        Candidate(
            xpath=LabXPaths.CODE_TRANSLATION_DISPLAY_NAME,
            value="LOINC translation",
            system="http://loinc.org",
        ),
    ]

    preference = get_evaluation_criteria_for_data_field(
        DataField.LAB_TEST_NAME_RESULTED
    ).translation_preference

    selected = evaluator._resolve_best_for_xpath(
        candidates=candidates,
        xpath=LabXPaths.CODE_TRANSLATION_DISPLAY_NAME,
        preference=preference,
    )

    assert selected == candidates[1]


def test_selects_code_display_name_when_present_and_non_empty() -> None:
    candidates = [
        Candidate(
            xpath=LabXPaths.CODE_DISPLAY_NAME,
            value="SARS-CoV-2 (COVID-19) RNA [Presence] in Specimen by NAA with probe detection",
            system=None,
        ),
        Candidate(
            xpath=LabXPaths.CODE_ORIGINAL_TEXT,
            value="COVID19 PCR QUALITATIVE",
            system=None,
        ),
    ]

    criteria = get_evaluation_criteria_for_data_field(DataField.LAB_TEST_NAME_RESULTED)

    selected = select_relevant_text(candidates=candidates, criteria=criteria)

    assert selected == candidates[0]


def test_falls_back_to_translation_display_name_when_code_display_name_missing() -> None:
    candidates = [
        Candidate(
            xpath=LabXPaths.CODE_TRANSLATION_DISPLAY_NAME,
            value="SARS-CoV-2 RNA Spec Ql NAA+probe",
            system="http://loinc.org",
        ),
        Candidate(
            xpath=LabXPaths.CODE_ORIGINAL_TEXT,
            value="COVID19 PCR QUALITATIVE",
            system=None,
        ),
    ]

    criteria = get_evaluation_criteria_for_data_field(DataField.LAB_TEST_NAME_RESULTED)

    selected = select_relevant_text(candidates=candidates, criteria=criteria)

    assert selected == candidates[0]


def test_prefers_loinc_translation_over_snomed_when_multiple_translation_display_names() -> None:
    candidates = [
        Candidate(
            xpath=LabXPaths.CODE_TRANSLATION_DISPLAY_NAME,
            value="Some SNOMED-ish text",
            system="http://snomed.info/sct",
        ),
        Candidate(
            xpath=LabXPaths.CODE_TRANSLATION_DISPLAY_NAME,
            value="Preferred LOINC text",
            system="http://loinc.org",
        ),
    ]

    criteria = get_evaluation_criteria_for_data_field(DataField.LAB_TEST_NAME_RESULTED)

    selected = select_relevant_text(candidates=candidates, criteria=criteria)

    assert selected == candidates[1]


def test_prefers_snomed_translation_when_no_loinc_translation_present() -> None:
    candidates = [
        Candidate(
            xpath=LabXPaths.CODE_TRANSLATION_DISPLAY_NAME,
            value="Preferred SNOMED text",
            system="http://snomed.info/sct",
        ),
        Candidate(
            xpath=LabXPaths.CODE_TRANSLATION_DISPLAY_NAME,
            value="Other translation text",
            system="urn:oid:9.9.9.9.9",
        ),
    ]

    criteria = get_evaluation_criteria_for_data_field(DataField.LAB_TEST_NAME_RESULTED)

    selected = select_relevant_text(candidates=candidates, criteria=criteria)

    assert selected == candidates[0]


def test_prefers_loinc_translation_original_text_when_multiple_translation_original_text_candidates() -> (
    None
):
    candidates = [
        Candidate(
            xpath=LabXPaths.CODE_TRANSLATION_ORIGINAL_TEXT,
            value="Some SNOMED original text",
            system="http://snomed.info/sct",
        ),
        Candidate(
            xpath=LabXPaths.CODE_TRANSLATION_ORIGINAL_TEXT,
            value="Preferred LOINC original text",
            system="http://loinc.org",
        ),
    ]

    criteria = get_evaluation_criteria_for_data_field(DataField.LAB_TEST_NAME_RESULTED)

    selected = select_relevant_text(candidates=candidates, criteria=criteria)

    assert selected == candidates[1]


def test_falls_back_to_code_original_text_when_code_display_name_is_blank() -> None:
    candidates = [
        Candidate(
            xpath=LabXPaths.CODE_DISPLAY_NAME,
            value="   ",
            system=None,
        ),
        Candidate(
            xpath=LabXPaths.CODE_ORIGINAL_TEXT,
            value="COVID19 PCR QUALITATIVE",
            system=None,
        ),
    ]

    criteria = get_evaluation_criteria_for_data_field(DataField.LAB_TEST_NAME_RESULTED)

    selected = select_relevant_text(candidates=candidates, criteria=criteria)

    assert selected == candidates[1]


def test_select_relevant_text_skips_candidate_when_value_is_none() -> None:
    candidates = [
        Candidate.model_construct(
            xpath=LabXPaths.CODE_DISPLAY_NAME,
            value=None,
            system=None,
        ),
        Candidate(
            xpath=LabXPaths.CODE_ORIGINAL_TEXT,
            value="COVID19 PCR QUALITATIVE",
            system=None,
        ),
    ]

    criteria = get_evaluation_criteria_for_data_field(DataField.LAB_TEST_NAME_RESULTED)

    selected = select_relevant_text(candidates=candidates, criteria=criteria)

    assert selected == candidates[1]


def test_returns_none_when_all_candidates_are_blank_or_missing_for_priorities() -> None:
    candidates = [
        Candidate(
            xpath=LabXPaths.CODE_DISPLAY_NAME,
            value="",
            system=None,
        ),
        Candidate(
            xpath=LabXPaths.CODE_TRANSLATION_DISPLAY_NAME,
            value="   ",
            system="http://loinc.org",
        ),
        Candidate(
            xpath=LabXPaths.CODE_ORIGINAL_TEXT,
            value="",
            system=None,
        ),
        Candidate(
            xpath=LabXPaths.CODE_TRANSLATION_ORIGINAL_TEXT,
            value="   ",
            system="http://snomed.info/sct",
        ),
    ]

    criteria = get_evaluation_criteria_for_data_field(DataField.LAB_TEST_NAME_RESULTED)

    selected = select_relevant_text(candidates=candidates, criteria=criteria)

    assert selected is None


def test_get_evaluation_criteria_for_data_field_returns_criteria_instance() -> None:
    criteria = get_evaluation_criteria_for_data_field(DataField.LAB_TEST_NAME_RESULTED)

    assert criteria is not None


def test_get_evaluation_criteria_for_data_field_raises_for_unregistered_data_field(mocker) -> None:
    class EmptyRegistry(dict):
        def __getitem__(self, key) -> KeyError:
            raise KeyError(key)

    mocker.patch.object(evaluator, "EVALUATION_REGISTRY", EmptyRegistry())

    with pytest.raises(
        KeyError,
        match=r"No evaluation criteria registered for DataField Lab Test Name Resulted",
    ):
        evaluator.get_evaluation_criteria_for_data_field(DataField.LAB_TEST_NAME_RESULTED)
