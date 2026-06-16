from huggingface_hub import errors, model_info

from shared_models import DataField
from text_to_code.models.labs import BaseLabField
from text_to_code.models.model_info import ModelInfo
from text_to_code.models.registry import EICR_REGISTRY

ConfigType = type[BaseLabField]


def get_config_for_data_field(data_field: DataField) -> BaseLabField:
    """Returns a fresh Pydantic config instance for a given data field.

    Uses defaults defined in the config model unless overridden.

    :param data_field: The data field of interest.
    :param kwargs: Any overrides to use when creating the config instance.
    :returns: A Pydantic config instance for the specified data field.
    """
    try:
        cls = EICR_REGISTRY[data_field]
    except KeyError as e:
        raise KeyError(f"No config registered for EicrDataField {data_field}") from e

    return cls()


def get_model_info(model: str) -> ModelInfo:
    """Returns the model info for a given model.

    :param model: The name of the model.
    :returns: The model info for the specified model.
    """
    try:
        full_info = model_info(model)
    # If the model doesn't exist or is inaccessible, model_info will return a 400 error
    except errors.RepositoryNotFoundError as e:
        raise ValueError(f"Model name '{model}' was not found") from e

    info = ModelInfo(
        id=full_info.id,
        author=full_info.author,
        created_at=full_info.created_at,
        last_modified=full_info.last_modified,
    )

    return info
