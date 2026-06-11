import logging

from lxml import etree

from shared_models import CdaInstanceIdentifier, DataField
from text_to_code.models.schematron import _SCHEMATRON_ENUM_TO_FIELD, SchematronErrorDetail

logger = logging.getLogger(__name__)


def get_data_element_from_schematron_error(schematron_error_id: str) -> DataField | None:
    """Return the data field that the error message is associated with, if any.

    :param schematron_error: The schematron error message being evaluated.
    :returns: The data field the schematron error is associated with,
        or None if not found.
    """
    for error_enum, data_field in _SCHEMATRON_ENUM_TO_FIELD.items():
        if schematron_error_id in (e.value for e in error_enum):
            return data_field
    return None


def _get_error_enum_value(schematron_error_id: str) -> str | None:
    """Return the normalized Schematron enum value for the error message, if any.

    :param schematron_error: The schematron error message being evaluated.
    :returns: The matching enum member value, or None if not found.
    """
    for error_enum in _SCHEMATRON_ENUM_TO_FIELD:
        for error in error_enum:
            if schematron_error_id == error.value:
                return error.value
    return None


def _get_eicr_id(xml_root: etree._Element) -> CdaInstanceIdentifier | None:
    """Return the eICR id from the ClinicalDocument, if present.

    :param xml_root: Parsed XML root element.
    :returns: The eICR identifier, or None if not found.
    """
    id_elem = xml_root.find(".//id")
    if id_elem is None:
        return None
    root = id_elem.get("root")
    extension = id_elem.get("extension")
    if root is None:
        return None
    return CdaInstanceIdentifier(root=root, extension=extension)


def get_data_fields_from_schematron_error(
    schematron_output: str,
) -> list[SchematronErrorDetail]:
    """Find errors that correspond to specific data elements/fields.

    :param schematron_output: The data from the Schematron validation
        run against the eICR document, containing errors that may
        be relevant for TTC processing.
    :returns: List of Schematron error details for TTC processing.
    """
    if not schematron_output.strip():
        return []

    xml_root = etree.fromstring(schematron_output.encode("utf-8"))
    eicr_id = _get_eicr_id(xml_root)
    schematron_errors: list[SchematronErrorDetail] = []

    validation_results = xml_root.xpath(".//*[local-name()='validationResult']")
    if etree.QName(xml_root).localname == "validationResult":
        validation_results.insert(0, xml_root)

    for vr in validation_results:
        try:
            issue = vr.find("issue")
            if issue is None:
                continue
            message_elem = issue.find("message")
            context_elem = issue.find("context")
            test_elem = issue.find("test")
            id_elem = issue.find("id")
            assertion_id_elem = issue.find("assertionID")
            if (
                message_elem is None
                or message_elem.text is None
                or context_elem is None
                or context_elem.text is None
            ):
                continue
            error_message = message_elem.text.strip()
            error_context = context_elem.text.strip()
            error_assertion_id = assertion_id_elem.text.strip()
            err_data_field = get_data_element_from_schematron_error(error_assertion_id)
            if err_data_field is None:
                continue
            error_value = _get_error_enum_value(error_assertion_id)
            if error_value is None:
                continue
            error_detail = SchematronErrorDetail(
                eicr_id=eicr_id,
                field=err_data_field,
                error=error_value,
                error_message=error_message,
                error_context=error_context,
                error_test=test_elem.text.strip()
                if test_elem is not None and test_elem.text is not None
                else vr.get("test"),
                error_id=(
                    id_elem.text.strip()
                    if id_elem is not None and id_elem.text is not None
                    else assertion_id_elem.text.strip()
                    if assertion_id_elem is not None and assertion_id_elem.text is not None
                    else vr.get("id") or issue.get("id")
                ),
                candidate=None,
            )
            if error_detail not in schematron_errors:
                schematron_errors.append(error_detail)
        except Exception:
            logger.exception(
                "Failed to process a schematron error detail",
                extra={
                    "error_id": assertion_id_elem.text if assertion_id_elem is not None else None,
                    "error_message": message_elem.text if message_elem is not None else None,
                    "error_context": context_elem.text if context_elem is not None else None,
                    "status": "error",
                },
            )
            continue

    return schematron_errors
