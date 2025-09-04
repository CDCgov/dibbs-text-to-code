from dibbs_text_to_code import augmentation


class TestScrambleWordOrder:
    def test_scramble_word_order_empty_string(self):
        result = augmentation.scramble_word_order("", max_perms=3)
        assert result == ""

    def test_scramble_word_order_single_word(self):
        result = augmentation.scramble_word_order("hello", max_perms=3)
        assert result == "hello"

    def test_scramble_word_order_multiple_words(self):
        text = "The quick brown fox jumps over the lazy dog"
        result = augmentation.scramble_word_order(text, max_perms=5)
        assert result != text

    def test_scramble_word_order_excess_perms(self):
        text = "One two three"
        result = augmentation.scramble_word_order(text, max_perms=10)
        assert result != text
