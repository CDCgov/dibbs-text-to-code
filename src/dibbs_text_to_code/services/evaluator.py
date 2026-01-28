from dibbs_text_to_code.models import DataField
from dibbs_text_to_code.services import utils


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
