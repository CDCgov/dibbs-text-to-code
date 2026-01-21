from dibbs_text_to_code import models

ConfigType = type[models.labs.BaseLabField]


def get_config_for_data_field(data_field: models.eicr.EicrDataField) -> models.labs.BaseLabField:
    """Returns a fresh Pydantic config instance for a given data field.

    Uses defaults defined in the config model unless overridden.

    :param data_field: The data field of interest.
    :param kwargs: Any overrides to use when creating the config instance.
    :returns: A Pydantic config instance for the specified data field.
    """
    try:
        cls = models.registry.EICR_REGISTRY[data_field]
    except KeyError as e:
        raise KeyError(f"No config registered for EicrDataField {data_field}") from e

    return cls()
