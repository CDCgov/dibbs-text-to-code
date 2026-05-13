from datetime import datetime
from uuid import NAMESPACE_URL
from uuid import uuid5

from lxml import etree
from lxml.etree import Element

from augmentation.models import ApplicationCode
from augmentation.models import Metadata
from augmentation.models import TTCAugmenterConfig
from augmentation.models.application import NonstandardCodeInstanceMetadata
from augmentation.services.augmenter import Augmenter
from shared_models import NonstandardCodeInstance

from .eicr_utils import CDA_NS
from .eicr_utils import CDA_NSMAP
from .eicr_utils import cda_xpath


def _cda_element(tag: str, parent: Element | None = None) -> Element:
    """Create an element in the CDA default namespace (urn:hl7-org:v3)."""
    full_tag = f"{{{CDA_NS}}}{tag}"
    if parent is not None:
        return etree.SubElement(parent, full_tag)
    return etree.Element(full_tag)


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
        deterministic_id_seed: str | None = None,
    ):
        """Initialize EICRAugmenter.

        For now only TTC is supported in Augmentation and the only document type for TTC is eICR.
        # TODO: for now just use hard coded TTC Config we will need to remove/change this once we have S3 config integrated
        """
        if config is None:
            config = TTCAugmenterConfig()

        super().__init__(document, config, ApplicationCode.TEXT_TO_CODE, augmentation_date)

        self.original_eicr_id = self._get_augmented_tag_by_xpath("/ClinicalDocument/id/@root")
        self.deterministic_id_seed = deterministic_id_seed or self.original_eicr_id
        self.new_doc_id: str = self._generate_deterministic_id("document")
        self.new_set_id: str = self._generate_deterministic_id("set")
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
        self._augmented_element.replace(old_id_element, new_id_element)

        # 2 replace the effectiveTime tag
        old_eff_time_element = self._get_augmented_tag_by_xpath("/ClinicalDocument/effectiveTime")
        self._add_previous_element_comment(
            "time of data augmentation operation ", old_eff_time_element
        )
        # we need to retain the old tags 'tail' to preserve the spacing format
        new_eff_time_element = self._get_new_effective_time()
        new_eff_time_element.tail = old_eff_time_element.tail
        self._augmented_element.replace(old_eff_time_element, new_eff_time_element)

        # 3 next replace the setId tag
        old_set_id_element = self._get_augmented_tag_by_xpath("/ClinicalDocument/setId")
        # we need to retain the old tags 'tail' to preserve the spacing format
        new_set_id_element = self._get_new_set_id()
        new_set_id_element.tail = old_set_id_element.tail
        self._add_previous_element_comment("new-document-setId ", old_set_id_element)
        self._augmented_element.replace(old_set_id_element, new_set_id_element)
        # 4 finally replace the versionNumber tag
        old_version_element = self._get_augmented_tag_by_xpath("/ClinicalDocument/versionNumber")
        # we need to retain the old tags 'tail' to preserve the spacing format
        new_version_element = self._get_new_version_number()
        new_version_element.tail = old_version_element.tail
        self._add_previous_element_comment("new-document-versionNumber ", old_version_element)
        self._augmented_element.replace(old_version_element, new_version_element)

        # 5 add the new templateId tag which will also include the comments in order
        template_id = self._get_augmented_template_id()
        # find the newly added and updated document id and put the templateId right before it
        new_id = self._get_augmented_tag_by_xpath("/ClinicalDocument/id")
        self._add_previous_element_comment("eICR Data Augmentation Header ", new_id)
        new_id.addprevious(template_id)
        self._add_previous_element_comment("new-document-id ", new_id)

    def _handle_related_document_header(self) -> None:
        """Add related document referencing the old eICR."""
        related_doc = _cda_element("relatedDocument", self._augmented_element)
        related_doc.set("typeCode", "XFRM")
        self._add_previous_element_comment(" typeCode 'XFRM' ", related_doc)
        parent_doc = _cda_element("parentDocument", related_doc)
        parent_doc_id = self._get_old_document_id()
        parent_doc.append(parent_doc_id)
        # comments need to be added to the element after it's been appended to the
        # parent data element
        self._add_previous_element_comment(
            "ClinicalDocument/id of the document to replace ", parent_doc_id
        )
        if parent_doc_id.get("assigningAuthorityName") == "original-document":
            self._add_previous_element_comment("original-document-id ", parent_doc_id)
        else:
            self._add_previous_element_comment("input-document-id ", parent_doc_id)
        parent_set_id = self._get_old_set_id()
        parent_doc.append(parent_set_id)
        self._add_previous_element_comment("input-document-setId ", parent_set_id)
        parent_version_number = self._get_old_version_number()
        parent_doc.append(parent_version_number)
        self._add_previous_element_comment("input-document-versionNumber ", parent_version_number)

    def _get_original_by_xpath(self, xpath: str) -> Element:
        """Get element from the original eICR by XPath."""
        return self._get_element_by_xpath(self._original_element, xpath)

    def _get_augmented_tag_by_xpath(self, xpath: str) -> Element:
        """Get element from the augmented eICR by XPath."""
        return self._get_element_by_xpath(self._augmented_element, xpath)

    def _get_element_by_xpath(self, element: Element, xpath: str) -> Element:
        """Get the first matching child element by XPath, or raise if not found."""
        results = element.xpath(cda_xpath(xpath), namespaces=CDA_NSMAP)
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

    def _generate_deterministic_id(self, identifier_type: str) -> str:
        """Generate a stable UUID for augmented eICR identifiers."""
        return str(
            uuid5(
                NAMESPACE_URL,
                f"{self._get_application_code_value()}:{self.deterministic_id_seed}:{identifier_type}",
            )
        )

    def _get_new_document_id(self) -> Element:
        """Generate a new document ID element for the augmented eICR document."""
        doc_id_tag = _cda_element("id")
        doc_id_tag.set("root", self.new_doc_id)
        doc_id_tag.set("assigningAuthorityName", self._get_application_code_value())
        return doc_id_tag

    def _get_new_set_id(self) -> Element:
        """Generate a new setId element for the augmented eICR document."""
        set_id_tag = _cda_element("setId")
        set_id_tag.set("root", self.new_set_id)
        return set_id_tag

    def _get_new_effective_time(self) -> Element:
        """Generate an effectiveTime element for the augmented eICR document."""
        effective_time_tag = _cda_element("effectiveTime")
        effective_time_tag.set("value", self.augmentation_date.strftime("%Y%m%d%H%M%S"))
        return effective_time_tag

    def _get_new_version_number(self) -> Element:
        """Generate a versionNumber element for the augmented eICR document."""
        old_version_number = self._get_old_version_number()
        version_number_tag = _cda_element("versionNumber")
        version_number_tag.set("value", old_version_number.get("value", "1"))
        return version_number_tag

    def _get_augmented_template_id(self) -> Element:
        """Generate a new templateId element for the augmented eICR document."""
        # this new templateId is defined in the Augmentation Spec V2
        template_id_tag = _cda_element("templateId")
        template_id_tag.set("root", "2.16.840.1.113883.10.20.15.2.1.3")
        template_id_tag.set("extension", "2025-11-01")
        return template_id_tag

    def _add_previous_element_comment(self, comment: str, element: Element) -> None:
        """Generate an XML comment element with the given comment text and add it before the specified element."""
        comment_element = etree.Comment(f"DATA AUGMENTATION: {comment.strip()} ")
        element.addprevious(comment_element)

    def _generate_author(self, level: str = "header") -> Element:
        null_flavor_comment = " set to nullFlavor 'NA' "
        author = _cda_element("author")
        # TODO: Eventually we will not only separate by header vs. data_element
        # but will also separate out the various comments by the various data element
        # type being modified. This can easily be stored in the model for the data element.
        # For now we are hard coding for code-text-to-code and observation in the comment
        if level != "header":
            function_code = _cda_element("functionCode", author)
            function_code.set("code", value=self.config.author_function_code)
            function_code.set("codeSystem", value=self.config.author_function_code_system)
            function_code.set("codeSystemName", value=self.config.author_function_code_system_name)
            self._add_previous_element_comment(
                (
                    "functionCode specifies type of change "
                    f"'{self.config.author_function_code}' which signifies that the code in this observation "
                    "has been augmented with a code derived from the text in the code element "
                ),
                function_code,
            )
        author_eff_time = self._get_new_effective_time()
        author.append(author_eff_time)
        self._add_previous_element_comment("time of data augmentation operation ", author_eff_time)
        if level == "header":
            self._add_previous_element_comment(
                (
                    "Header-level Author to flag that this document "
                    "has been transformed on the platform (e.g. to add text-to-code information) "
                    "The functionCode holds the tool used/type of transform (e.g. text-to-code) "
                    "and the time holds the time of the transformation/operation "
                ),
                author,
            )
        assigned_author = _cda_element("assignedAuthor", author)
        id = _cda_element("id", assigned_author)
        id.set("nullFlavor", "NA")
        self._add_previous_element_comment(null_flavor_comment, id)
        addr = _cda_element("addr", assigned_author)
        addr.set("nullFlavor", "NA")
        self._add_previous_element_comment(null_flavor_comment, addr)
        telecom = _cda_element("telecom", assigned_author)
        telecom.set("nullFlavor", "NA")
        self._add_previous_element_comment(null_flavor_comment, telecom)
        assigned_authoring_device = _cda_element("assignedAuthoringDevice", assigned_author)
        self._add_previous_element_comment(
            " set to 'Data Augmentation Tool' ", assigned_authoring_device
        )
        software_name = _cda_element("softwareName", assigned_authoring_device)
        software_name.set("code", value=self._get_application_code_value())
        software_name.set("codeSystem", value=self.config.author_function_code_system)
        software_name.set("codeSystemName", value=self.config.author_function_code_system_name)
        software_name.set("displayName", self._get_application_code_display())
        self._add_previous_element_comment(
            " assignedAuthoringDevice/softwareName specifies that this document has been transformed using the Text-to-Code data augmentation tool",
            software_name,
        )

        return author

    def _handle_author_header(self) -> None:
        """Generate and add to the augment eICR document an author element."""
        author = self._generate_author(level="header")
        self._augmented_element.append(author)

    def _handle_author_entry(self, augmentation: NonstandardCodeInstance) -> None:
        entry = self._get_augmented_tag_by_xpath(augmentation.schematron_error_xpath)
        author = self._generate_author(level="data_element")
        entry.append(author)

    # TODO: this will need to be modified in the future when we have
    # other data elements, other than observation.codes that are being augmented
    def _handle_translation(self, augmentation: NonstandardCodeInstance) -> str:
        entry_code = self._get_augmented_tag_by_xpath(augmentation.schematron_error_xpath + "/code")
        self._add_previous_element_comment(
            "This data has been augmented with a standard LOINC code", entry_code
        )
        self._add_previous_element_comment(
            "The data in the code and code/originalText data elements is the original data",
            entry_code,
        )
        new_translation = _cda_element("translation", entry_code)
        _set_attribute(new_translation, "code", augmentation.new_translation.code)
        new_translation.set("codeSystem", "2.16.840.1.113883.6.1")
        new_translation.set("codeSystemName", "LOINC")
        _set_attribute(new_translation, "DisplayName", augmentation.new_translation.display_name)
        _set_attribute(new_translation, "originalText", augmentation.new_translation.original_text)
        self._add_previous_element_comment(
            "The data in the translation is the augmented data", new_translation
        )

        return _absolute_local_xpath(new_translation)


def _set_attribute(element: Element, key: str, value: str | None) -> None:
    if value:
        element.set(key, value)


def _absolute_local_xpath(element: Element) -> str:
    """Build an absolute XPath using local element names.

    Adds a 1-based positional index `[N]` only when siblings share the same
    local tag, so that unique elements yield clean paths like
    `/ClinicalDocument/component/.../translation` while ambiguous ones remain
    addressable.
    """
    parts: list[str] = []
    current: Element | None = element
    while current is not None:
        local = etree.QName(current).localname
        parent = current.getparent()
        if parent is not None:
            same_tag_siblings = [
                c
                for c in parent
                if not isinstance(c, etree._Comment) and etree.QName(c).localname == local
            ]
            if len(same_tag_siblings) > 1:
                idx = same_tag_siblings.index(current) + 1
                parts.append(f"{local}[{idx}]")
            else:
                parts.append(local)
        else:
            parts.append(local)
        current = parent
    return "/" + "/".join(reversed(parts))
