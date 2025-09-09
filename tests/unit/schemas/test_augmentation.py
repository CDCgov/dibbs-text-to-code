import pytest

from dibbs_text_to_code.schemas import augmentation


class TestAugmentation:
    def test_LoincEnhancements(self):
        data = {
            "abbreviations": ["abbr1", "abbr2"],
            "acronyms": ["acro1", "acro2"],
            "replacement": ["repl1", "repl2"],
        }
        loinc_enhancements = augmentation.LoincEnhancements(**data)
        assert loinc_enhancements.abbreviations == data["abbreviations"]
        assert loinc_enhancements.acronyms == data["acronyms"]
        assert loinc_enhancements.replacement == data["replacement"]

    def test_LoincEnhancements_invalid(self):
        data = {
            "abbreviations": "not a list",
            "acronyms": ["acro1", "acro2"],
            "replacement": ["repl1", "repl2"],
        }
        with pytest.raises(ValueError):
            augmentation.LoincEnhancements(**data)

    def test_LoincEnhancements_empty(self):
        data = {
            "abbreviations": [],
            "acronyms": [],
            "replacement": [],
        }
        loinc_enhancements = augmentation.LoincEnhancements(**data)
        assert loinc_enhancements.abbreviations == []
        assert loinc_enhancements.acronyms == []
        assert loinc_enhancements.replacement == []

    def test_LoincEnhancements_None(self):
        data = {
            "abbreviations": None,
            "acronyms": None,
            "replacement": None,
        }
        with pytest.raises(ValueError):
            augmentation.LoincEnhancements(**data)
