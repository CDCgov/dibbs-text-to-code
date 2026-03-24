import copy
from abc import ABC
from abc import abstractmethod
from datetime import datetime

from lxml import etree
from lxml.etree import Element

from augmentation.models import Metadata

from ..models.application import ApplicationCode
from ..models.config import AugmenterConfig
from .eicr_utils import clean_xml_tree


class Augmenter(ABC):
    """Augments a document (e.g., eICR) with additional information using a validated config."""

    def __init__(
        self,
        document: str,
        config: AugmenterConfig,
        application_code: ApplicationCode = ApplicationCode.TEXT_TO_CODE,
        augmentation_date: datetime | None = None,
    ):
        """Initialize Augmenter."""
        self.original_xml = document
        self._original_element = self.document_payload_not_none(self.original_xml)
        self._augmented_element = copy.deepcopy(self._original_element)

        self.application_code = application_code
        self.config = self._validate_config(config)
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
        return clean_xml_tree(v)

    def _get_application_code_value(self) -> str:
        # added this check to satisfy the type checker
        # we will never return an ""
        if hasattr(self.application_code, "code"):
            return self.application_code.code
        return ""

    def _get_application_code_display(self) -> str:
        # added this check to satisfy the type checker
        # we will never return an ""
        if hasattr(self.application_code, "display"):
            return self.application_code.display
        return ""

    @abstractmethod
    def augment(self) -> Metadata:
        """Internal method to perform augmentation logic."""
        pass

    def _validate_config(self, _config: AugmenterConfig) -> AugmenterConfig:
        """Validates that the config matches the application and document type."""
        if _config.application_code != self.application_code:
            raise ValueError(
                f"Config application code {_config.application_code} does not match Augmenter application code {self.application_code}."
            )
        return _config
