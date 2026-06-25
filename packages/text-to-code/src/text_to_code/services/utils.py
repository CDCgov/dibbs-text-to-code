import logging
import os

from huggingface_hub import errors, model_info

from shared_models import DataField
from text_to_code.models.labs import BaseLabField
from text_to_code.models.model_info import ModelInfo
from text_to_code.models.registry import EICR_REGISTRY

logger = logging.getLogger(__name__)

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

    Models baked into the container image are referenced by a local filesystem
    path (e.g. ``/opt/retriever_model``) rather than a Hugging Face repo id.
    Such a path is not a valid repo id, and the Hub is unreachable from the
    production VPC anyway, so for local paths we skip the Hub lookup and return
    only the id. The remaining fields are populated from the Hub when the model
    is a reachable repo id.

    :param model: The Hugging Face repo id or local filesystem path of the model.
    :returns: The model info for the specified model.
    """
    # Models baked into the image load from a local path, which is not a valid
    # Hub repo id and cannot be looked up (the prod VPC has no internet access).
    if os.path.isdir(model):
        logger.info("Model '%s' is a local path; skipping Hugging Face Hub lookup.", model)
        return ModelInfo(id=model, author=None, created_at=None, last_modified=None)

    try:
        full_info = model_info(model)
    # If the model doesn't exist or is inaccessible, model_info will return a 400 error
    except errors.RepositoryNotFoundError as e:
        raise ValueError(f"Model name '{model}' was not found") from e
    # A value that is neither a local path nor a valid repo id must not crash
    # module import; degrade gracefully to just the id.
    except errors.HFValidationError:
        logger.warning(
            "Model '%s' is not a valid Hugging Face repo id; skipping Hub lookup.", model
        )
        return ModelInfo(id=model, author=None, created_at=None, last_modified=None)

    info = ModelInfo(
        id=full_info.id,
        author=full_info.author,
        created_at=full_info.created_at,
        last_modified=full_info.last_modified,
    )

    return info
