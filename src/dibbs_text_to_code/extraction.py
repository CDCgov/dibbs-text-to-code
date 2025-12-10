from dibbs_text_to_code import configs


def _is_valid_data_field(data_field: str) -> bool:
    if data_field.strip() not in configs.DATA_FIELDS:
        return False
    return True


def _meets_word_count(text: str, word_count: int) -> bool:
    if len(text.split()) > word_count:
        return True
    return False


def is_text_viable(data_field: str, text: str) -> bool:
    """Verifies if a text string is viable for evaluation within
    the TTC model for a specified data field (ie. 'Lab Result')

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
