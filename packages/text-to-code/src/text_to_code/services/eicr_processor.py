import logging

from lxml import etree
from lxml.etree import Element

from shared_models import CdaInstanceIdentifier, DataField
from text_to_code.models import Candidate
from text_to_code.models.eicr import Metadata, TextCandidateExtractionLogContext
from text_to_code.services.utils import get_config_for_data_field

logger = logging.getLogger(__name__)


class EicrProcessor:
    """Processes an eICR."""

    def __init__(self, eicr_data: str):
        """Initialize an eICR Processor.

        :param eicr_data: string of eICR
        """
        self._xml_root = _create_xml_tree(eicr_data)

    def _get_by_xpath(self, xpath: str) -> Element:
        return self._xml_root.xpath(xpath)

    def get_text_candidates(self, base_xpath: str, data_field: DataField) -> list[Candidate]:
        """Find text candidates for a specified data field/element.

        :param base_xpath: The base XPath to use to find text candidates
            within the eICR for the specified data field.
        :param data_field: The data field of interest for TTC processing.
        :returns: A list of individual Candidates found within the eICR for
            the specified data field for TTC processing.
        """
        candidates: list[Candidate] = []
        extraction_error_count = 0
        no_candidate_count = 0
        # first get data field config settings - this acts
        # as a validation of correct data field being passed
        config_settings = get_config_for_data_field(data_field)

        if not base_xpath.strip() or config_settings is None:
            return candidates

        # get list of xpaths per data field from config
        sub_xpaths = config_settings.xpaths
        log_context = TextCandidateExtractionLogContext(
            base_xpath=base_xpath,
            data_field=data_field,
            sub_xpaths=sub_xpaths,
        )

        try:
            nodes = self._get_by_xpath(base_xpath)
        except etree.XPathError:
            self._log_text_candidate_extraction_error(
                log_context=log_context,
                extraction_error_count=1,
            )
            return candidates

        for _ in nodes:
            for sub_xpath in sub_xpaths:
                full_xpath = f"{base_xpath}/{sub_xpath}"

                try:
                    sub_nodes = self._get_by_xpath(full_xpath)
                except etree.XPathError:
                    extraction_error_count += 1
                    self._log_text_candidate_extraction_error(
                        log_context=log_context,
                        extraction_error_count=extraction_error_count,
                        sub_xpath=sub_xpath,
                        full_xpath=full_xpath,
                    )
                    continue

                if not sub_nodes:
                    no_candidate_count += 1
                    continue

                for sub_node in sub_nodes:
                    try:
                        candidate_added = self._append_text_candidates_from_sub_node(
                            candidates=candidates,
                            sub_node=sub_node,
                            xpath=sub_xpath,
                        )
                    except (etree.XPathError, AttributeError, ValueError):
                        extraction_error_count += 1
                        self._log_text_candidate_extraction_error(
                            log_context=log_context,
                            extraction_error_count=extraction_error_count,
                            sub_xpath=sub_xpath,
                            full_xpath=full_xpath,
                        )
                        continue

                    if not candidate_added:
                        no_candidate_count += 1

        self._log_text_candidate_extraction_summary(
            candidates=candidates,
            log_context=log_context,
            extraction_error_count=extraction_error_count,
            no_candidate_count=no_candidate_count,
        )
        return candidates

    def _append_text_candidates_from_sub_node(
        self, candidates: list[Candidate], sub_node: Element | str, xpath: str
    ) -> bool:
        """Append text candidates from a sub-node to the list of candidates.

        :param candidates: The list of candidates to append to.
        :param sub_node: The sub-node to extract text from.
        :param xpath: The XPath of the sub-node.
        :return: True if any candidates were added, False otherwise.
        """
        candidate_count = len(candidates)

        if isinstance(sub_node, str):
            text: str = sub_node.strip()
            if text:
                candidates.append(Candidate(value=text, xpath=xpath))
        else:
            texts = self._extract_text_candidates_from_element(sub_node)
            for text in texts:
                candidates.append(Candidate(value=text, xpath=xpath))

        return len(candidates) > candidate_count

    def _log_text_candidate_extraction_error(
        self,
        log_context: TextCandidateExtractionLogContext,
        extraction_error_count: int,
        sub_xpath: str | None = None,
        full_xpath: str | None = None,
    ) -> None:
        """Log an error that occurred during text candidate extraction.

        :param log_context: The context for logging.
        :param extraction_error_count: The number of errors that have occurred so far.
        :param sub_xpath: The sub-XPath that caused the error, if applicable.
        :param full_xpath: The full XPath that caused the error, if applicable.
        """
        logger.exception(
            "Failed to extract text candidates from eICR",
            extra={
                "base_xpath": log_context.base_xpath,
                "data_field": str(log_context.data_field),
                "sub_xpaths": log_context.sub_xpaths,
                "sub_xpath": sub_xpath,
                "full_xpath": full_xpath,
                "status": "error",
                "metric_name": "eicr_text_candidates_extraction_raised",
                "extraction_error_count": extraction_error_count,
            },
        )

    def _log_text_candidate_extraction_summary(
        self,
        candidates: list[Candidate],
        log_context: TextCandidateExtractionLogContext,
        extraction_error_count: int,
        no_candidate_count: int,
    ) -> None:
        """Log a summary of the text candidate extraction process.

        :param candidates: The list of candidates extracted.
        :param log_context: The context for logging.
        :param extraction_error_count: The number of errors that occurred during extraction.
        :param no_candidate_count: The number of times no candidates were found for a sub-X
        """
        if not candidates and extraction_error_count == 0:
            logger.info(
                "No text candidates found in eICR",
                extra={
                    "base_xpath": log_context.base_xpath,
                    "data_field": str(log_context.data_field),
                    "sub_xpaths": log_context.sub_xpaths,
                    "status": "no_candidates",
                    "metric_name": "eicr_text_candidates_no_candidates",
                    "no_candidate_count": no_candidate_count,
                },
            )

        if extraction_error_count > 0:
            logger.warning(
                "Completed eICR text candidate extraction with errors",
                extra={
                    "base_xpath": log_context.base_xpath,
                    "data_field": str(log_context.data_field),
                    "sub_xpaths": log_context.sub_xpaths,
                    "status": "error",
                    "metric_name": "eicr_text_candidates_extraction_raised",
                    "extraction_error_count": extraction_error_count,
                    "candidate_count": len(candidates),
                },
            )

    def resolve_reference(self, reference_value: str | None) -> str | None:
        """Get the text of the first node with an ID attribute that matches the reference."""
        reference_value = reference_value.strip() if reference_value else ""
        if not reference_value:
            return None

        referenced_node = self._xml_root.find(f'.//*[@ID="{reference_value.strip("#")}"]')

        if referenced_node is not None:
            return " ".join(_get_text_recursively(referenced_node))

        return None

    def _extract_text_candidates_from_element(self, element: Element) -> list[str]:
        """Extract text candidates from an element.

        :param element: The XML element.
        :returns: A list of text candidates extracted from the element.
        """
        candidates: list[str] = []
        text_parts: list[str] = []

        if element.text:
            text_parts.append(element.text.strip())

        for child in element:
            # Handle reference elements
            if child.tag == "reference":
                ref_text = self.resolve_reference(child.get("value"))
                if ref_text:
                    candidates.append(ref_text)
            else:
                # Recursively get text from child elements
                text_parts.extend(_get_text_recursively(child))

            if child.tail:
                text_parts.append(child.tail.strip())

        original_text = " ".join(filter(None, text_parts))
        if original_text:
            candidates.insert(0, original_text)

        return candidates

    @property
    def eicr_metadata(self) -> Metadata:
        """Get the eICR ID from the XML."""
        id_element = self._xml_root.find(".//id")
        if id_element is None or id_element.get("nullFlavor") is not None:
            logger.warning("No ID element found in eICR XML.")
            instance_identifier = None
        else:
            instance_identifier = CdaInstanceIdentifier(
                root=id_element.get("root"),
                extension=id_element.get("extension"),
                assigning_authority_name=id_element.get("assigningAuthorityName"),
                displayable=_to_bool(id_element.get("displayable")),
                null_flavor=id_element.get("nullFlavor"),
            )
        vendor = self._xml_root.find(
            ".//author/assignedAuthor/assignedAuthoringDevice/softwareName"
        )
        return Metadata(
            eicr_id=instance_identifier, eicr_vendor=vendor.text if vendor is not None else None
        )


def _to_bool(value: str | None) -> bool | None:
    if value is None:
        return None
    if value.lower() == "true":
        return True
    if value.lower() == "false":
        return False
    return None


def _create_xml_tree(xml: str) -> Element:
    """Remove all namespaces from an XML tree."""
    tree = etree.fromstring(xml.encode("utf-8"))
    for elem in tree.iter():
        # Skip comment nodes — their .tag is a callable, not a QName-compatible string
        if not isinstance(elem, etree._Comment):
            elem.tag = etree.QName(elem).localname
    # Remove namespace declarations
    etree.cleanup_namespaces(tree)
    return tree


def _get_text_recursively(element: Element) -> list[str]:
    text_elements: list[str] = []
    if element.text:
        text_elements.append(element.text.strip())

    for child in element:
        text_elements += _get_text_recursively(child)

    if element.tail:
        text_elements.append(element.tail.strip())

    return list(filter(lambda x: x, text_elements))
