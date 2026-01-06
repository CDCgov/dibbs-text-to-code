from configs.general import EicrConfig
from configs.general import SCHEMATRON_ERRORS


def get_data_field_config(data_field: str):
    """Verifies a specified data field is in focus for the TTC module
    and if it is, will return the class configuration settings for that data field.
    Otherwise, returns None.

    :param data_field: The data field/element, from an eICR, that
        is being evaluated within the TTC module.
    :returns: A configuration setting class for the data field it it is
        within focus, or None, for the TTC module.
    """
    try:
        data_field_config_class = EicrConfig[data_field.strip()].value.__class__
        return data_field_config_class()
    except KeyError:
        return None


def get_data_field_by_schematron_error(schematron_error: str) -> str | None:
    """Given a schematron error message, will return the data field/element
    that the error message is associated with, if any.

    :param schematron_error: The schematron error message being evaluated.
    :returns: The data field/element the schematron error is associated with,
        or None if not found.
    """
    for data_field, error_list in SCHEMATRON_ERRORS.items():
        if schematron_error in error_list:
            return data_field
    return None
