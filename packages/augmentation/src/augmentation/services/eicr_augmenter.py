from datetime import datetime
from uuid import uuid4

from lxml import etree
from lxml.etree import Element
from shared_models import NonstandardCodeInstance

from augmentation.models import ApplicationCode
from augmentation.models import Metadata
from augmentation.models import TTCAugmenterConfig
from augmentation.models.application import NonstandardCodeInstanceMetadata
from augmentation.services.augmenter import Augmenter


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
        nonstandard_codes: list[NonstandardCodeInstance],
        config: TTCAugmenterConfig | None = None,
        augmentation_date: datetime | None = None,
    ):
        """Initialize EICRAugmenter.

        For now only TTC is supported in Augmentation and the only document type for TTC is eICR.
        # TODO: for now just use hard coded TTC Config we will need to remove/change this once we have S3 config integrated
        """
        if config is None:
            config = TTCAugmenterConfig()

        super().__init__(document, config, ApplicationCode.TEXT_TO_CODE, augmentation_date)

        self.original_eicr_id = self._get_augmented_tag_by_xpath("/ClinicalDocument/id/@root")
        self.new_doc_id: str = str(uuid4())
        self.new_set_id: str = str(uuid4())
        self.nonstandard_codes = nonstandard_codes

    def augment(self) -> Metadata:
        """Apply augmentation to the eICR."""
        # Document level rules
        if "document_id_header" in self.config.rules["document"]:
            self._handle_document_id_header()
            self._handle_related_document_header()
        if "author_header" in self.config.rules["document"]:
            self._handle_author_header()

        nonstandard_code_metadata: list[NonstandardCodeInstanceMetadata] = []

        for nonstandard_code_instance in self.nonstandard_codes:
            data_type_rules = self.config.rules[nonstandard_code_instance.field_type]
            if "author_entry" in data_type_rules:
                self._handle_author_entry(nonstandard_code_instance)
            if "translation" in data_type_rules:
                new_translation_path = self._handle_translation(nonstandard_code_instance)

            nonstandard_code_metadata.append(
                NonstandardCodeInstanceMetadata(
                    schematron_error=nonstandard_code_instance.schematron_error,
                    schematron_error_xpath=nonstandard_code_instance.schematron_error_xpath,
                    field_type=nonstandard_code_instance.field_type,
                    new_translation=nonstandard_code_instance.new_translation,
                    new_translation_xpath=new_translation_path,
                )
            )

        metadata = Metadata(
            original_eicr_id=self.original_eicr_id,  # ty:ignore[invalid-argument-type]
            augmented_eicr_id=self.new_doc_id,
            nonstandard_codes=nonstandard_code_metadata,
        )
        return metadata

    def _handle_document_id_header(self) -> None:
        # 1 first replace the id tag
        old_id_element = self._get_augmented_tag_by_xpath("/ClinicalDocument/id")
        # we need to retain the old tags 'tail' to preserve the spacing format
        new_id_element = self._get_new_document_id()
        new_id_element.tail = old_id_element.tail
        self._add_previous_element_comment("new-document-id", new_id_element)
        self._augmented_element.replace(old_id_element, new_id_element)

        # 2 replace the effectiveTime tag
        old_eff_time_element = self._get_augmented_tag_by_xpath("/ClinicalDocument/effectiveTime")
        # we need to retain the old tags 'tail' to preserve the spacing format
        new_eff_time_element = self._get_new_effective_time()
        new_eff_time_element.tail = old_eff_time_element.tail
        self._add_previous_element_comment(
            "time of data augmentation operation", new_eff_time_element
        )
        self._augmented_element.replace(old_eff_time_element, new_eff_time_element)

        # 3 next replace the setId tag
        old_set_id_element = self._get_augmented_tag_by_xpath("/ClinicalDocument/setId")
        # we need to retain the old tags 'tail' to preserve the spacing format
        new_set_id_element = self._get_new_set_id()
        new_set_id_element.tail = old_set_id_element.tail
        self._add_previous_element_comment("new-document-setId", new_set_id_element)
        self._augmented_element.replace(old_set_id_element, new_set_id_element)
        # 4 finally replace the versionNumber tag
        old_version_element = self._get_augmented_tag_by_xpath("/ClinicalDocument/versionNumber")
        # we need to retain the old tags 'tail' to preserve the spacing format
        new_version_element = self._get_new_version_number()
        new_version_element.tail = old_version_element.tail
        self._add_previous_element_comment("new-document-versionNumber", new_version_element)
        self._augmented_element.replace(old_version_element, new_version_element)
        # 5 add the new templateId tag
        template_id = self._get_augmented_template_id()
        self._add_previous_element_comment("eICR Data Augmentation Header", template_id)
        # find the newly added and updated document id and put the templateId right before it
        new_id = self._get_augmented_tag_by_xpath("/ClinicalDocument/id")
        new_id.addprevious(template_id)

    def _handle_related_document_header(self) -> None:
        """Add related document referencing the old eICR."""
        related_doc = etree.SubElement(self._augmented_element, "relatedDocument")
        related_doc.set("typeCode", "XFRM")
        parent_doc = etree.SubElement(related_doc, "parentDocument")
        parent_doc.append(self._get_old_document_id())
        parent_doc.append(self._get_old_set_id())
        parent_doc.append(self._get_old_version_number())

    def _get_original_by_xpath(self, xpath: str) -> Element:
        """Get element from the original eICR by XPath."""
        return self._get_element_by_xpath(self._original_element, xpath)

    def _get_augmented_tag_by_xpath(self, xpath: str) -> Element:
        """Get element from the augmented eICR by XPath."""
        return self._get_element_by_xpath(self._augmented_element, xpath)

    def _get_element_by_xpath(self, element: Element, xpath: str) -> Element:
        """Get the first matching child element by XPath, or raise if not found."""
        results = element.xpath(xpath)
        if not results:
            raise ValueError(f"Unable to find tag in eICR document for XPath: {xpath}")
        return results[0]

    def _get_old_document_id(self) -> Element:
        """Extract the parent document ID from original eICR document."""
        parent_doc_id = self._get_original_by_xpath("/ClinicalDocument/id")
        if parent_doc_id.get("assigningAuthorityName") is None:
            parent_doc_id.set("assigningAuthorityName", "original-document")
        return parent_doc_id

    def _get_old_set_id(self) -> Element:
        """Extract the parent document setId from original eICR document."""
        parent_set_id = self._get_original_by_xpath("/ClinicalDocument/setId")
        return parent_set_id

    def _get_old_version_number(self) -> Element:
        """Extract the parent versionNumber from original eICR document."""
        version = self._get_original_by_xpath("/ClinicalDocument/versionNumber")
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

    def _get_augmented_template_id(self) -> Element:
        """Generate a new templateId element for the augmented eICR document."""
        # this new templateId is defined in the Augmentation Spec V2
        template_id_tag = etree.Element("templateId")
        template_id_tag.set("root", "2.16.840.1.113883.10.20.15.2.1.3")
        template_id_tag.set("extension", "2025-11-01")
        return template_id_tag

    def _add_previous_element_comment(self, comment: str, element: Element) -> None:
        """Generate an XML comment element with the given comment text and add it before the specified element."""
        comment_element = etree.Comment(f"DATA AUGMENTATION: {comment}")
        element.addprevious(comment_element)

    def _get_old_xrfm_related_document(self) -> Element | None:
        """Extract the relatedDocument tag with typeCode "XFRM" from original eICR document."""
        try:
            return self._get_augmented_tag_by_xpath(
                "/ClinicalDocument/relatedDocument[@typeCode='XFRM']"
            )
        except ValueError:
            # if the relatedDocument with typeCode "XFRM" doesn't exist then return None
            return None

    def _generate_author(self) -> Element:
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

        return author

    def _handle_author_header(self) -> None:
        """Generate and add to the augment eICR document an author element."""
        author = self._generate_author()
        self._augmented_element.append(author)

    def _handle_author_entry(self, augmentation: NonstandardCodeInstance) -> None:
        entry = self._get_augmented_tag_by_xpath(augmentation.schematron_error_xpath)
        author = self._generate_author()
        entry.append(author)

    def _handle_translation(self, augmentation: NonstandardCodeInstance) -> str:
        entry_code = self._get_augmented_tag_by_xpath(augmentation.schematron_error_xpath + "/code")

        new_translation = etree.SubElement(entry_code, "translation")
        _set_attribute(new_translation, "code", augmentation.new_translation.code)
        new_translation.set("codeSystem", "2.16.840.1.113883.6.1")
        new_translation.set("codeSystemName", "LOINC")
        _set_attribute(new_translation, "DisplayName", augmentation.new_translation.display_name)
        _set_attribute(new_translation, "originalText", augmentation.new_translation.original_text)

        return self._augmented_element.getroottree().getpath(new_translation)


def _set_attribute(element: Element, key: str, value: str | None) -> None:
    if value:
        element.set(key, value)
