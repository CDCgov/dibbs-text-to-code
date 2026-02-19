import importlib

import pytest
from text_to_code.models.eicr import Candidate
from text_to_code.models.eicr import DataField
from text_to_code.models.eicr import LabXPaths
from text_to_code.services.evaluator import get_evaluation_criteria_for_data_field
from text_to_code.services.evaluator import select_relevant_text


def _patch_is_text_viable(monkeypatch: pytest.MonkeyPatch, fn: callable) -> None:
    module = importlib.import_module(select_relevant_text.__module__)
    monkeypatch.setattr(module, "is_text_viable", fn)


def test_selects_code_display_name_when_present_and_viable(monkeypatch: pytest.MonkeyPatch) -> None:
    def _is_text_viable(_: DataField, __: str) -> bool:
        return True

    _patch_is_text_viable(monkeypatch, _is_text_viable)

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

    assert (
        selected == "SARS-CoV-2 (COVID-19) RNA [Presence] in Specimen by NAA with probe detection"
    )


def test_falls_back_to_translation_display_name_when_code_display_name_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _is_text_viable(_: DataField, __: str) -> bool:
        return True

    _patch_is_text_viable(monkeypatch, _is_text_viable)

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

    assert selected == "SARS-CoV-2 RNA Spec Ql NAA+probe"


def test_prefers_loinc_translation_over_snomed_when_multiple_translation_display_names(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _is_text_viable(_: DataField, __: str) -> bool:
        return True

    _patch_is_text_viable(monkeypatch, _is_text_viable)

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

    assert selected == "Preferred LOINC text"


def test_prefers_snomed_translation_when_no_loinc_translation_present(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _is_text_viable(_: DataField, __: str) -> bool:
        return True

    _patch_is_text_viable(monkeypatch, _is_text_viable)

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

    assert selected == "Preferred SNOMED text"


def test_falls_back_to_code_original_text_when_display_names_unviable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _is_text_viable(_: DataField, text: str) -> bool:
        return text != "Bad display name"

    _patch_is_text_viable(monkeypatch, _is_text_viable)

    candidates = [
        Candidate(
            xpath=LabXPaths.CODE_DISPLAY_NAME,
            value="Bad display name",
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

    assert selected == "COVID19 PCR QUALITATIVE"


def test_returns_none_when_no_candidate_is_viable(monkeypatch: pytest.MonkeyPatch) -> None:
    def _is_text_viable(_: DataField, __: str) -> bool:
        return False

    _patch_is_text_viable(monkeypatch, _is_text_viable)

    candidates = [
        Candidate(
            xpath=LabXPaths.CODE_DISPLAY_NAME,
            value="Anything",
            system=None,
        ),
        Candidate(
            xpath=LabXPaths.CODE_TRANSLATION_DISPLAY_NAME,
            value="Anything else",
            system="http://loinc.org",
        ),
        Candidate(
            xpath=LabXPaths.CODE_ORIGINAL_TEXT,
            value="Anything more",
            system=None,
        ),
        Candidate(
            xpath=LabXPaths.CODE_TRANSLATION_ORIGINAL_TEXT,
            value="More still",
            system="http://snomed.info/sct",
        ),
    ]

    criteria = get_evaluation_criteria_for_data_field(DataField.LAB_TEST_NAME_RESULTED)

    selected = select_relevant_text(candidates=candidates, criteria=criteria)

    assert selected is None
