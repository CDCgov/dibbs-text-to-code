import copy
from abc import ABC, abstractmethod
from datetime import datetime

from lxml import etree
from lxml.etree import Element

from augmentation.models import Metadata

from ..models.application import ApplicationCode
from .eicr_utils import parse_eicr_xml


class Augmenter(ABC):
    """Augments a document (e.g., eICR) with additional information using a validated config."""

    def __init__(
        self,
        document: str,
        application_code: ApplicationCode = ApplicationCode.TEXT_TO_CODE,
        augmentation_date: datetime | None = None,
    ):
        """Initialize Augmenter."""
        self.original_xml = document
        self._original_element = self.document_payload_not_none(self.original_xml)
        self._augmented_element = copy.deepcopy(self._original_element)

        self.application_code = application_code
        self.augmentation_date = datetime.now() if augmentation_date is None else augmentation_date

    @property
    def augmented_xml(self) -> str:
        """Get the augmented XML document as a string."""
        etree.indent(self._augmented_element, space="    ")
        return etree.tostring(
            self._augmented_element, pretty_print=True, encoding="utf-8", xml_declaration=True
        ).decode()

    @classmethod
    def document_payload_not_none(cls, v: str) -> Element:
        """Validates that the document payload is always supplied as a non-empty string."""
        if v is None or v.strip() == "":
            raise ValueError("Document payload must be a non-empty string!")
        return parse_eicr_xml(v)

    def _get_application_code_value(self) -> str:
        return self.application_code.code

    def _get_application_code_display(self) -> str:
        return self.application_code.display

    @abstractmethod
    def augment(self) -> Metadata:
        """Internal method to perform augmentation logic."""
        pass
