import pytest

from dibbs_text_to_code import augmentation


@pytest.mark.parametrize(
    "text, max_perms, expected",
    [
        # Empty string
        ("", 3, ""),
        # Single word
        ("Blood", 3, "Blood"),
        # Multiple words with special characters
        (
            "SARS-CoV-2 E gene Resp Ql NAA+probe",
            5,
            "E gene Resp SARS-CoV-2 Ql NAA+probe",
        ),
        # More deletions than words
        ("B pert Spt Ql Cult", 10, "Spt pert B Ql Cult"),
    ],
)
class TestScrambleWordOrder:
    def test_scramble_word_order(self, text, max_perms, expected):
        result = augmentation.scramble_word_order(text, max_perms=max_perms)
        assert result == expected


class TestCharDeletion:
    def test_random_char_deletion(self):
        test_string = "HERE IS my TEST09: string       yes  crudblahtest    "
        result = augmentation.random_char_deletion(test_string, 3, 8, 2, "char")
        print(f"STR {len(test_string)}: {test_string}")
        print(f"HERE {len(result)}: {result}")
        assert test_string != result

    def test_random_char_deletion_word(self):
        test_string = "HERE IS my TEST09: string       yes  crudblahtest    "
        result = augmentation.random_char_deletion(test_string, 1, 2, 2, "word")
        print(f"STR {len(test_string)}: {test_string}")
        print(f"HERE {len(result)}: {result}")
        assert 1 == 2
