from sentence_transformers import SentenceTransformer
from torch import Tensor

from dibbs_text_to_code.configs.general import _model_name as default_model_name
from dibbs_text_to_code.configs.general import get_configuration_for_data_element


class Evaluator:
    """Evaluates and transforms nonstandard text."""

    _model: SentenceTransformer | None = None

    def __init__(self, model_name: str = default_model_name):
        """Initialize evaluator.

        :model_name: Model name string.
        """
        self._model_name = model_name

    def embed(self, input_text: str) -> Tensor:
        """Take a text string and embeds it as a vector using a model as defined in config.py.

        :param input_text: Text string to embed.
        :returns: Tensor representation of input text.
        """
        if self._model is None:
            self._model = SentenceTransformer(self._model_name)
        return self._model.encode(input_text)


def _meets_word_count(text: str, word_count: int) -> bool:
    """Verify if the number of words within a given text string meets the word count rule supplied.

    :param text: The text string being evaluated.
    :param word_count: The number of words required for
        a given data field, based upon the configured rule.
    :returns: A boolean (True or False) if the text meets the
        word count rule criteria or not.
    """
    return len(text.split()) > word_count


def is_text_viable(data_field: str, text: str) -> bool:
    """Verify a text string is viable for evaluation for a specified data field, i.e. 'Lab Result'.

    :param data_field: The data field/element, from an eICR, that
        is being evaluated within the TTC module.
    :param text: The text string being evaluated, for a given
        data_field, to see if it's viable for evaluation in
        the TTC module based upon data_field specific rules.
    :returns: A boolean (True or False) if the text for a data_field is
        viable for TTC or not.
    """
    result = False
    # verify the data type is a proper one
    data_field_config = get_configuration_for_data_element(data_field)
    if data_field_config is None:
        return result

    # ensure the data type is 'in scope' for TTC processing
    if len(data_field_config.schematron_errors) == 0:
        return result

    # first test word count if such a rule is present in the
    # config for the specified data element
    word_count_rule = data_field_config.text_word_count
    if word_count_rule and word_count_rule > 0:
        result = _meets_word_count(text, word_count_rule)

    return result
