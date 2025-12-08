from api.config import DATA_FIELD_TEXT_RULES
from api.config import DATA_FIELDS


def _is_valid_data_field(data_field: str) -> bool:
    if data_field.strip() not in DATA_FIELDS:
        return False
    else:
        return True


def is_text_viable(data_field: str, text: str) -> bool:
    """
    Verifies if a text string is viable for evaluation within
    the TTC model for a specified data field (ie. 'Lab Result')

    :param data_field: The data field/element, from an eICR, that
        is being evaluated within the TTC.
    :param text: The text string being evaluated to see if it's
        viable for evaluation in the TTC module or not, for the
        given data element.
    :returns: A boolean (True or False).
    """
    if not _is_valid_data_field(data_field) or not text.strip():
        return False

    # get all the data rules for the field
    data_field_rules = DATA_FIELD_TEXT_RULES.get(data_field)

    if not data_field_rules:
        return False

    # first get and test the field length
    data_field_length = data_field_rules.get("text_length")

    if data_field_length and len(text.split()) > data_field_length:
        return True
    return False
