from lxml import etree
from sentence_transformers import SentenceTransformer
from torch import Tensor

from dibbs_text_to_code.configs import DATA_FIELD_TEXT_RULES
from dibbs_text_to_code.configs import DATA_FIELDS
from dibbs_text_to_code.configs import MODEL_NAME
from dibbs_text_to_code.configs import SCHEMATRON_ERRORS

MODEL: SentenceTransformer | None = None


def _set_sentence_transformer(model_name: str = MODEL_NAME):
    global MODEL
    if MODEL is None:
        model = SentenceTransformer(model_name)
        MODEL = model


def embed(input_text: str) -> Tensor:
    """Takes a text string and embeds it as vectorspip
    using a model as defined in config.py.

    :param input_text: Text string to embed.
    :returns: Tensor representation of input text.
    """
    _set_sentence_transformer(MODEL_NAME)
    return MODEL.encode(input_text)


def _is_valid_data_field(data_field: str) -> bool:
    """Verifies a specified data field is in focus for the TTC module.

    :param data_field: The data field/element, from an eICR, that
        is being evaluated within the TTC module.
    :returns: A boolean (True or False) if the data field is
        within focus, or not, for the TTC module.
    """
    return data_field.strip() in DATA_FIELDS


def _meets_word_count(text: str, word_count: int) -> bool:
    """Verifies if the number of words witin a given text string meets the word count rule supplied.

    :param text: The text string being evaluated.
    :param word_count: The number of words required for
        a given data field, based upon the configured rule.
    :returns: A boolean (True or False) if the text meets the
        word count rule criteria or not.
    """
    return len(text.split()) > word_count


def is_text_viable(data_field: str, text: str) -> bool:
    """Verifies if a text string is viable for evaluation within the TTC model for a specified data field (ie. 'Lab Result').

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
    data_field_rules = DATA_FIELD_TEXT_RULES.get(data_field)

    if not data_field_rules:
        return False

    # first test word count if such a rule is present in the
    # config for the specified data element
    word_count_rule = data_field_rules.get("text_word_count")
    if word_count_rule and word_count_rule > 0:
        result = _meets_word_count(text, word_count_rule)

    return result


def get_data_fields_from_schematron_error(schematron_output: str) -> dict:
    """Using the output from the Schematron validation, find errors that
    correspond to specific data elements/fields within the eICR that
    TTC needs to try to find codes for.

    :param schematron_output: The data from the Schematron validation
        run against the eICR document, containing errors that may
        be relevant for TTC processing.
    :returns: Dictionary of Data Field name and list of XPaths of where
        to find data within the eICR for TTC processing.
    """
    data_fields_with_context = {}
    if not schematron_output.strip():
        return data_fields_with_context

    xml_root = etree.fromstring(schematron_output.encode("utf-8"))
    # loop through schematron validation results
    # TODO: I tried using the 'finall' method, but it was erroring out
    #  for now just loop through children tags under the root
    for result in xml_root:
        try:
            for vr in result.findall("validationResult"):
                if vr is None:
                    continue
                issue = vr.find("issue")
                msg = issue.find("message").text
                if issue is None or msg is None:
                    continue
                # check if the msg alings with any of the
                # specified schematron errors for various data fields
                for data_field, error_msgs in SCHEMATRON_ERRORS.items():
                    if msg in error_msgs:
                        xpath = issue.find("context").text
                        if data_fields_with_context.get(data_field) is None:
                            data_fields_with_context[data_field] = []
                        # if the xpath for a particular data field is already
                        # account for, don't duplicate it
                        if xpath not in data_fields_with_context[data_field]:
                            data_fields_with_context[data_field].append(xpath)

        except Exception as e:
            # TODO: we may want to log this somewhere instead of print
            print(f"Error parsing schematron output: {e}")
            continue
    return data_fields_with_context


def _enhance_base_xpath(base_xpath: str, namespace: str) -> str:
    """Enhance a base XPath with the specified namespace.

    :param base_xpath: The base XPath to enhance.
    :param namespace: The namespace to apply to the base XPath.
    :returns: The enhanced XPath with the specified namespace.
    """
    # split the xpath into parts
    parts = base_xpath.strip().split("/")
    enhanced_parts = []
    for part in parts:
        if part == "ClinicalDocument":
            continue
        if (
            part
            and not part.startswith(namespace + ":")
            and part.startswith("@") is False
            and part.endswith("()") is False
        ):
            enhanced_parts.append(f"{namespace}:{part}")
        else:
            enhanced_parts.append(part)
    enhanced_xpath = "." + "/".join(enhanced_parts)
    return enhanced_xpath


def get_text_candidates(eicr_data: str, base_xpath: str, data_field: str) -> list:
    """Using the eICR data and a base XPath, find text candidates
    for a specified data field/element to be used in the TTC module.

    :param eicr_data: The eICR data as an XML string.
    :param base_xpath: The base XPath to use to find text candidates
        within the eICR for the specified data field.
    :param data_field: The data field/element of interest for TTC processing.
    :returns: A list of text candidates found within the eICR for
        the specified data field/element for TTC processing.
    """

    text_candidates = []
    namespaces = {"cda": "urn:hl7-org:v3"}
    if (
        eicr_data.strip() is None
        or base_xpath.strip() is None
        or not base_xpath.strip()
        or not _is_valid_data_field(data_field)
    ):
        return text_candidates

    # first get list of xpaths per data field from config
    xpaths = DATA_FIELD_TEXT_RULES.get(data_field, {}).get("x_paths", [])

    # enhance the base xpath with the namespace
    base_xpath = _enhance_base_xpath(base_xpath, "cda")

    try:
        xml_root = etree.fromstring(eicr_data.encode("utf-8"))
        nodes = xml_root.xpath(base_xpath, namespaces=namespaces)
        for node in nodes:
            for xpath in xpaths:
                enhanced_xpath = _enhance_base_xpath(xpath, "cda")
                sub_nodes = node.xpath(enhanced_xpath, namespaces=namespaces)
                for i, sub_node in enumerate(sub_nodes):
                    if len(sub_node.strip()) > 0:
                        # TODO: do we need to store the base xpath
                        # and more specific xpath used to get the text WITH the text like below?
                        # text_candidates[sub_node.strip()] = {"base_xpath": base_xpath, "x_path": enhanced_xpath, "iteration": i}
                        text_candidates.append(sub_node.strip())
    except Exception as e:
        # TODO: we may want to log this somewhere instead of print
        print(f"Error extracting text from eicr message: {e}")
        return text_candidates
    return text_candidates
