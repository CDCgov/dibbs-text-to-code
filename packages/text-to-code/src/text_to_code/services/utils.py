from hashlib import sha256

from shared_models import DataField
from text_to_code.models.labs import BaseLabField
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


def compute_cache_key(*text: str) -> str:
    """Compute cache key by hashing the concatenation of the given strings."""
    return sha256((" | ".join(x.strip().lower() for x in text)).encode("utf-8")).hexdigest()
