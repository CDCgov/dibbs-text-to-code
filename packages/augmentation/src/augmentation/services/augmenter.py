import copy
from abc import ABC
from abc import abstractmethod
from datetime import datetime
from functools import cached_property
from uuid import uuid4

from lxml import etree
from lxml.etree import Element
from pydantic import ConfigDict

from ..models.application import ApplicationCode
from ..models.config import AugmenterConfig
from ..models.config import TTCAugmenterConfig
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
        self.document: str = self.document_payload_not_none(document)
        self.application_code = application_code
        self.config = self._validate_config(config)
        self.augmentation_date = datetime.now() if augmentation_date is None else augmentation_date

    @classmethod
    def document_payload_not_none(cls, v: str) -> str:
        """Validates that the document payload is always supplied as a non-empty string."""
        if v is None or v.strip() == "":
            raise ValueError("Document payload must be a non-empty string!")
        return v

    def _get_application_code_value(self) -> str:
        return self.application_code.value

    def run(self) -> str:
        """Execute augmentation process on the document payload."""
        # This is a placeholder for the actual augmentation logic.
        self.augmented_document = self._augment()  # No actual augmentation done here YET.
        return self.augmented_document

    @abstractmethod
    def _augment(self) -> str:
        """Internal method to perform augmentation logic."""
        pass

    def _validate_config(self, _config: AugmenterConfig) -> AugmenterConfig:
        """Validates that the config matches the application and document type."""
        if _config.application_code != self.application_code:
            raise ValueError(
                f"Config application code {_config.application_code} does not match Augmenter application code {self.application_code}."
            )
        return _config


class EICRAugmenter(Augmenter):
    """Augmenter specific to eICR documents.

    It is expected that the document payload will be
    an eICR document and therefore the class should
    automatically set various attributes specific to eICRs.
    """

    config: TTCAugmenterConfig

    def __init__(
        self,
        document: str,
        augmentation_date: datetime | None = None,
    ):
        """Initialize EICRAugmenter.

        For now only TTC is supported in Augmentation and the only document type for TTC is eICR.
        # TODO: for now just use hard coded TTC Config we will need to remove/change this once we have S3 config integrated
        """
        super().__init__(
            document, TTCAugmenterConfig(), ApplicationCode.TEXT_TO_CODE, augmentation_date
        )

        self.new_doc_id: str = str(uuid4())
        self.new_set_id: str = str(uuid4())
        self.model_config = ConfigDict(arbitrary_types_allowed=True)

    @cached_property
    def original_eicr(self) -> Element:
        """CLeaned and parsed document into an XML Element."""
        return clean_xml_tree(self.document)

    # make copy of original eICR to modify as we augment
    # TODO: I don't like having multiple copies of the payload
    # but we do need two so that we can pull data from the original, while
    # also being able to modify the augmented version.
    # I ran into issues either in tests or in typing that made me
    # land on this approach, but I'm open to refactoring this in
    # the future if we can find a better way to handle it.
    @cached_property
    def augmented_eicr(self) -> Element:
        """Deep copy of cleaned document_payload specific for augmentation."""
        return copy.deepcopy(self.original_eicr)

    def _augment(self) -> str:
        # Document level rules
        if "document_id_header" in self.config.rules["document"]:
            self._handle_document_id_header()
            self._handle_related_document_header()
        if "author_header" in self.config.rules["document"]:
            self._handle_author_header()

        etree.indent(self.augmented_eicr, space="    ")
        return etree.tostring(
            self.augmented_eicr, pretty_print=True, encoding="utf-8", xml_declaration=True
        ).decode()

    def _handle_document_id_header(self) -> None:
        # 1 first replace the id tag
        old_id_element = self._get_augmented_tag_by_xpath("/ClinicalDocument/id")
        # we need to retain the old tags 'tail' to preserve the spacing format
        new_id_element = self._get_new_document_id()
        new_id_element.tail = old_id_element.tail
        self.augmented_eicr.replace(old_id_element, new_id_element)

        # 2 replace the effectiveTime tag
        old_eff_time_element = self._get_augmented_tag_by_xpath("/ClinicalDocument/effectiveTime")
        # we need to retain the old tags 'tail' to preserve the spacing format
        new_eff_time_element = self._get_new_effective_time()
        new_eff_time_element.tail = old_eff_time_element.tail
        self.augmented_eicr.replace(old_eff_time_element, new_eff_time_element)
        # 3 next replace the setId tag if
        old_set_id_element = self._get_augmented_tag_by_xpath("/ClinicalDocument/setId")
        # we need to retain the old tags 'tail' to preserve the spacing format
        new_set_id_element = self._get_new_set_id()
        new_set_id_element.tail = old_set_id_element.tail
        self.augmented_eicr.replace(old_set_id_element, new_set_id_element)
        # 4 finally replace the versionNumber tag
        old_version_element = self._get_augmented_tag_by_xpath("/ClinicalDocument/versionNumber")
        # we need to retain the old tags 'tail' to preserve the spacing format
        new_version_element = self._get_new_version_number()
        new_version_element.tail = old_version_element.tail
        self.augmented_eicr.replace(old_version_element, new_version_element)

    def _handle_related_document_header(self) -> None:
        # 1 first determine if a relatedDocument with type "XFRM" exists
        related_doc_tag = self._get_old_xrfm_related_document()
        if related_doc_tag is None:
            # if it doesn't exist then create one and add it to the eICR
            new_related_doc = etree.SubElement(
                self.augmented_eicr.xpath("/ClinicalDocument")[0],
                "relatedDocument",
                typeCode="XFRM",
            )
            new_related_doc.tail = "\n\t"  # add text to preserve formatting
            new_parent_doc = etree.SubElement(new_related_doc, "parentDocument")
            new_parent_doc.append(self._get_old_document_id())
            new_parent_doc.append(self._get_old_set_id())
            new_parent_doc.append(self._get_old_version_number())
            new_parent_doc.tail = "\n\t\t"  # add text to preserve formatting
        # if relatedDocument/parentDocument already exists ensure that the original_document id
        # doesn't already exist in this section
        else:
            for doc_id in related_doc_tag.xpath("./id"):
                if doc_id.get("root") == self._get_old_document_id().get("root"):
                    return
            id_comment = etree.Comment("DATA AUGMENTATION: input-document-id of augmented eICR")
            related_doc_tag.append(id_comment)
            related_doc_tag.append(self._get_old_document_id())
            setid_comment = etree.Comment(
                "DATA AUGMENTATION: input-document-setId of augmented eICR"
            )
            related_doc_tag.append(setid_comment)
            related_doc_tag.append(self._get_old_set_id())
            version_comment = etree.Comment(
                "DATA AUGMENTATION: input-document-version-number of augmented eICR"
            )
            related_doc_tag.append(version_comment)
            related_doc_tag.append(self._get_old_version_number())

    def _get_original_by_xpath(self, xpath: str) -> Element:
        if self.original_eicr is None:
            raise ValueError("Original eICR document is empty.")
        return self.original_eicr.xpath(xpath)

    def _get_augmented_tag_by_xpath(self, xpath: str) -> Element:
        if self.augmented_eicr is None:
            raise ValueError("Augmented eICR document is empty.")
        augmented_tags = self.augmented_eicr.xpath(xpath)
        if not augmented_tags or len(augmented_tags) == 0:
            raise ValueError(f"Unable to find tag in augmented eICR document for XPath: {xpath}")
        return augmented_tags[0]

    def _get_old_document_id(self) -> Element:
        """Extract the parent document ID from original eICR document."""
        doc_id_elements = self._get_original_by_xpath("/ClinicalDocument/id")
        if not doc_id_elements or len(doc_id_elements) == 0:
            raise ValueError("No document ID found in eICR document.")
        parent_doc_id = doc_id_elements[0]
        if parent_doc_id.get("assigningAuthorityName") is None:
            parent_doc_id.set("assigningAuthorityName", "original-document")
        return parent_doc_id

    def _get_old_set_id(self) -> Element:
        """Extract the parent document setId from original eICR document."""
        set_id_elements = self._get_original_by_xpath("/ClinicalDocument/setId")
        if not set_id_elements or len(set_id_elements) == 0:
            raise ValueError("No document setId found in eICR document.")
        parent_set_id = set_id_elements[0]
        return parent_set_id

    def _get_old_version_number(self) -> Element:
        """Extract the parent versionNumber from original eICR document."""
        version_elements = self._get_original_by_xpath("/ClinicalDocument/versionNumber")
        if not version_elements or len(version_elements) == 0:
            raise ValueError("No document versionNumber found in eICR document.")
        version = version_elements[0]
        return version

    def _get_new_document_id(self) -> Element:
        """Generate a new document ID element for the augmented eICR document."""
        doc_id_tag = etree.Element("id")
        doc_id_tag.set("root", self.new_doc_id)
        doc_id_tag.set("assigningAuthorityName", self._get_application_code_value())
        return doc_id_tag

    def _get_new_set_id(self) -> Element:
        """Generate a new setId element for the augmented eICR document."""
        set_id_tag = etree.Element("setId")
        set_id_tag.set("root", self.new_set_id)
        return set_id_tag

    def _get_new_effective_time(self) -> Element:
        """Generate an effectiveTime element for the augmented eICR document."""
        effective_time_tag = etree.Element("effectiveTime")
        effective_time_tag.set("value", self.augmentation_date.strftime("%Y%m%d%H%M%S"))
        return effective_time_tag

    def _get_new_version_number(self) -> Element:
        """Generate a versionNumber element for the augmented eICR document."""
        version_number_tag = etree.Element("versionNumber")
        # hard code to 1 for now
        # TODO: we may need to have some way to increment this later
        version_number_tag.set("value", "1")
        return version_number_tag

    def _get_old_xrfm_related_document(self) -> Element | None:
        """Extract the relatedDocument tag with typeCode "XFRM" from original eICR document."""
        try:
            related_doc_elements = self._get_augmented_tag_by_xpath(
                "/ClinicalDocument/relatedDocument[@typeCode='XFRM']"
            )
            related_doc_element = related_doc_elements[0]
            return related_doc_element
        except ValueError:
            # if the relatedDocument with typeCode "XFRM" doesn't exist then return None
            return None

    def _handle_author_header(self) -> None:
        """Generate and add to the augment eICR document an author element."""
        author = etree.Element("author")
        function_code = etree.SubElement(author, "functionCode")
        function_code.set("code", value=self.config.author_function_code)
        function_code.set("codeSystem", value=self.config.author_function_code_system)
        function_code.set("codeSystemName", value=self.config.author_function_code_system_name)
        author.append(self._get_new_effective_time())
        assigned_author = etree.SubElement(author, "assignedAuthor")
        id = etree.SubElement(assigned_author, "id")
        id.set("nullFlavor", "NA")
        addr = etree.SubElement(assigned_author, "addr")
        addr.set("nullFlavor", "NA")
        telecom = etree.SubElement(assigned_author, "telecom")
        telecom.set("nullFlavor", "NA")
        assigned_authoring_device = etree.SubElement(assigned_author, "assignedAuthoringDevice")
        software_name = etree.SubElement(assigned_authoring_device, "softwareName")
        software_name.set("displayName", "Data Augmentation Tool")

        self.augmented_eicr.append(author)
