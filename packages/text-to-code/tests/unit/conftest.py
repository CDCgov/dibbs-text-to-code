import pytest

from text_to_code.services.evaluator import _get_evaluation_criteria_for_data_field
from text_to_code.services.utils import get_config_for_data_field


@pytest.fixture(autouse=True)
def _clear_memoized_registry_lookups():
    """Reset the registry lookup caches so tests that patch the registries stay isolated."""
    get_config_for_data_field.cache_clear()
    _get_evaluation_criteria_for_data_field.cache_clear()
    yield
    get_config_for_data_field.cache_clear()
    _get_evaluation_criteria_for_data_field.cache_clear()
