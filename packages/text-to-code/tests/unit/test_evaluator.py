import re

import pytest

from shared_models import LOINC_URL, LOINC_URN, SNOMED_URL, SNOMED_URN, DataField
from text_to_code.models.eicr import Candidate, LabXPaths
from text_to_code.models.evaluator import (
    LabTestNameResultedEvaluationCriteria,
    TranslationPreference,
    TranslationSelectionStrategy,
)
from text_to_code.services import evaluator as evaluator_service
from text_to_code.services.evaluator import select_relevant_text


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

    selected = select_relevant_text(candidates, DataField.LAB_TEST_NAME_RESULTED)

    assert selected == candidates[0]


def test_falls_back_to_translation_display_name_when_code_display_name_missing() -> None:
    candidates = [
        Candidate(
            xpath=LabXPaths.CODE_TRANSLATION_DISPLAY_NAME,
            value="SARS-CoV-2 RNA Spec Ql NAA+probe",
            system=LOINC_URL,
        ),
        Candidate(
            xpath=LabXPaths.CODE_ORIGINAL_TEXT,
            value="COVID19 PCR QUALITATIVE",
            system=None,
        ),
    ]

    selected = select_relevant_text(candidates, DataField.LAB_TEST_NAME_RESULTED)

    assert selected == candidates[0]


def test_prefers_loinc_translation_over_snomed_when_multiple_translation_display_names() -> None:
    candidates = [
        Candidate(
            xpath=LabXPaths.CODE_TRANSLATION_DISPLAY_NAME,
            value="Some SNOMED-ish text",
            system=SNOMED_URL,
        ),
        Candidate(
            xpath=LabXPaths.CODE_TRANSLATION_DISPLAY_NAME,
            value="Preferred LOINC text",
            system=LOINC_URL,
        ),
    ]

    selected = select_relevant_text(candidates, DataField.LAB_TEST_NAME_RESULTED)

    assert selected == candidates[1]


def test_prefers_snomed_translation_when_no_loinc_translation_present() -> None:
    candidates = [
        Candidate(
            xpath=LabXPaths.CODE_TRANSLATION_DISPLAY_NAME,
            value="Preferred SNOMED text",
            system=SNOMED_URL,
        ),
        Candidate(
            xpath=LabXPaths.CODE_TRANSLATION_DISPLAY_NAME,
            value="Other translation text",
            system="urn:oid:9.9.9.9.9",
        ),
    ]

    selected = select_relevant_text(candidates, DataField.LAB_TEST_NAME_RESULTED)

    assert selected == candidates[0]


def test_prefers_loinc_translation_original_text_when_multiple_translation_original_text_candidates() -> (
    None
):
    candidates = [
        Candidate(
            xpath=LabXPaths.CODE_TRANSLATION_ORIGINAL_TEXT,
            value="Some SNOMED original text",
            system=SNOMED_URL,
        ),
        Candidate(
            xpath=LabXPaths.CODE_TRANSLATION_ORIGINAL_TEXT,
            value="Preferred LOINC original text",
            system=LOINC_URL,
        ),
    ]

    selected = select_relevant_text(candidates, DataField.LAB_TEST_NAME_RESULTED)

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

    selected = select_relevant_text(candidates, DataField.LAB_TEST_NAME_RESULTED)

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
            system=LOINC_URL,
        ),
        Candidate(
            xpath=LabXPaths.CODE_ORIGINAL_TEXT,
            value="",
            system=None,
        ),
        Candidate(
            xpath=LabXPaths.CODE_TRANSLATION_ORIGINAL_TEXT,
            value="   ",
            system=SNOMED_URL,
        ),
    ]

    selected = select_relevant_text(candidates, DataField.LAB_TEST_NAME_RESULTED)

    assert selected is None


def test_select_relevant_text_selection_strategy_first(mocker):
    mocked_criteria = LabTestNameResultedEvaluationCriteria(
        translation_preference=TranslationPreference(
            strategy=TranslationSelectionStrategy.FIRST,
            loinc_system_values=[
                LOINC_URL,
                LOINC_URN,
            ],
            snomed_system_values=[
                SNOMED_URL,
                SNOMED_URN,
            ],
        )
    )

    mocker.patch.dict(
        "text_to_code.models.evaluator.EVALUATION_REGISTRY",
        {DataField.LAB_TEST_NAME_RESULTED: lambda: mocked_criteria},
    )

    candidates = [
        Candidate(
            xpath=LabXPaths.CODE_TRANSLATION_DISPLAY_NAME,
            value="SARS-CoV-2 (COVID-19) RNA [Presence] in Specimen by NAA with probe detection",
            system=None,
        ),
        Candidate(
            xpath=LabXPaths.CODE_TRANSLATION_DISPLAY_NAME,
            value="Something else, but Loinc",
            system=SNOMED_URL,
        ),
    ]

    actual = select_relevant_text(candidates, DataField.LAB_TEST_NAME_RESULTED)

    assert actual == candidates[0]


def test_select_relevant_text_no_systems():
    candidates = [
        Candidate(
            xpath=LabXPaths.CODE_TRANSLATION_DISPLAY_NAME,
            value="SARS-CoV-2 (COVID-19) RNA [Presence] in Specimen by NAA with probe detection",
            system=None,
        )
    ]

    actual = select_relevant_text(candidates, DataField.LAB_TEST_NAME_RESULTED)

    assert actual == candidates[0]


def test_select_relevant_text_not_loinc_or_snomed_system():
    candidates = [
        Candidate(
            xpath=LabXPaths.CODE_TRANSLATION_DISPLAY_NAME,
            value="SARS-CoV-2 (COVID-19) RNA [Presence] in Specimen by NAA with probe detection",
            system="Something else",
        )
    ]

    actual = select_relevant_text(candidates, DataField.LAB_TEST_NAME_RESULTED)

    assert actual == candidates[0]


def test_select_relevant_text_raises_for_unregistered_data_field(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    data_field = next(iter(evaluator_service.EVALUATION_REGISTRY.keys()))

    monkeypatch.setattr(evaluator_service, "EVALUATION_REGISTRY", {})

    with pytest.raises(
        KeyError,
        match=re.escape(f"No evaluation criteria registered for DataField {data_field}"),
    ):
        select_relevant_text(candidates=[], field_type=data_field)
