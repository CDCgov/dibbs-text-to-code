import utils.regex_patterns as rp


def normalize_text(text: str) -> str:
    """
    Normalize text for comparison by removing non-alphanumeric characters,
    converting to lowercase, and removing all trailing, leading, and excess whitespace.
    """
    text = rp.ALPHA_NUMERIC.sub(" ", text)

    return " ".join(text.strip().lower().split())
