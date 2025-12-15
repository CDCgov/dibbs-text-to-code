from sentence_transformers import SentenceTransformer
from torch import Tensor

from dibbs_text_to_code import configs

_model = None


def _get_sentence_transformer():
    _model = SentenceTransformer(configs.MODEL_NAME)


def embed(input_text: str) -> Tensor:
    """Takes a text string and embeds it as vectorspip
    using a model as defined in config.py.

    :param input_text: Text string to embed.
    :returns: Tensor representation of input text.
    """
    if _model is None:
        _get_sentence_transformer()
    return _model.encode(input_text)


def _is_valid_data_field(data_field: str) -> bool:
    """Verifies a specified data field is in focus for the TTC module.

    :param data_field: The data field/element, from an eICR, that
        is being evaluated within the TTC module.
    :returns: A boolean (True or False) if the data field is
        within focus, or not, for the TTC module.
    """
    return data_field.strip() in configs.DATA_FIELDS


def _meets_word_count(text: str, word_count: int) -> bool:
    """Verifies if the number of words witin a given text string meets the word count rule supplied.

    :param text: The text string being evaluated.
    :param word_count: The number of words required for
        a given data field, based upon the configured rule.
    :returns: A boolean (True or False) if the text meets the
        word count rule criteria or not.
    """
    return len(text.split()) > word_count


def is_text_viable(data_field: str, text: str) -> bool:
    """Verifies if a text string is viable for evaluation within the TTC model for a specified data field (ie. 'Lab Result').

    :param data_field: The data field/element, from an eICR, that
        is being evaluated within the TTC module.
    :param text: The text string being evaluated, for a given
        data_field, to see if it's viable for evaluation in
        the TTC module based upon data_field specific rules.
    :returns: A boolean (True or False) if the text for a data_field is
        viable for TTC or not.
    """
    result = False
    if not _is_valid_data_field(data_field) or not text.strip():
        return False

    # get all the data rules for the field
    data_field_rules = configs.DATA_FIELD_TEXT_RULES.get(data_field)

    if not data_field_rules:
        return False

    # first test word count if such a rule is present in the
    # config for the specified data element
    word_count_rule = data_field_rules.get("text_word_count")
    if word_count_rule and word_count_rule > 0:
        result = _meets_word_count(text, word_count_rule)

    return result
