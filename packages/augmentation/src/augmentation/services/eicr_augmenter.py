import copy
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import NAMESPACE_URL, uuid5

from lxml import etree
from lxml.etree import Element

from augmentation.models import Metadata, NonstandardCodeInstanceMetadata
from augmentation.services.eicr_utils import CDA_NSMAP, cda_element, cda_xpath, parse_document
from shared_models import CdaInstanceIdentifier, NonstandardCodeInstance

_AUTHOR_FUNCTION_CODE: str = "code-text-to-code"
_AUTHOR_FUNCTION_CODE_SYSTEM: str = "2.16.840.1.113883.10.20.15.2.7.1"
_AUTHOR_FUNCTION_CODE_SYSTEM_NAME: str = "eCRDataAugmentation"
_APPLICATION_CODE_VALUE: str = "text-to-code"
_APPLICATION_CODE_DISPLAY: str = "Text-to-Code"


@dataclass(frozen=True)
class AugmentResult:
    """The augmented XML and the associated metadata."""

    augmented_xml: str
    metadata: Metadata


class EICRAugmenter:
    """Augmenter specific to eICR documents.

    It is expected that the document payload will be
    an eICR document and therefore the class should
    automatically set various attributes specific to eICRs.
    """

    def __init__(
        self,
        document: str,
        nonstandard_codes: list[NonstandardCodeInstance],
        deterministic_id_seed: str | None = None,
    ):
        """Initialize EICRAugmenter with an eICR XML document and the nonstandard codes to resolve."""
        self.original_xml = document
        self._original_element = parse_document(self.original_xml)
        self._augmented_element = copy.deepcopy(self._original_element)

        self.augmentation_date = datetime.now(UTC)

        self.original_eicr_id = CdaInstanceIdentifier(
            root=self._get_augmented_attribute_by_xpath("/ClinicalDocument/id/@root"),
            extension=self._get_optional_augmented_attribute_by_xpath(
                "/ClinicalDocument/id/@extension"
            ),
        )
        self.deterministic_id_seed = (
            deterministic_id_seed
            or self.original_eicr_id.root
            or self.original_eicr_id.extension
            or ""
        )
        self.new_doc_id: str = self._generate_deterministic_id("document")
        self.new_set_id: str = self._generate_deterministic_id("set")
        self.nonstandard_codes = nonstandard_codes

    def augment(self) -> AugmentResult:
        """Apply augmentation to the eICR."""
        self._handle_document_id_header()
        self._handle_related_document_header()
        self._augmented_element.append(self._generate_author())

        nonstandard_code_metadata: list[NonstandardCodeInstanceMetadata] = []

        for nonstandard_code_instance in self.nonstandard_codes:
            self._handle_author_entry(nonstandard_code_instance)
            new_translation_path = self._handle_translation(nonstandard_code_instance)

            nonstandard_code_metadata.append(
                NonstandardCodeInstanceMetadata(
                    schematron_error_xpath=nonstandard_code_instance.schematron_error_xpath,
                    field_type=nonstandard_code_instance.field_type,
                    new_translation=nonstandard_code_instance.new_translation,
                    new_translation_xpath=new_translation_path,
                )
            )

        etree.indent(self._augmented_element, space="    ")
        augmented_xml = etree.tostring(
            self._augmented_element, pretty_print=True, encoding="utf-8", xml_declaration=True
        ).decode()

        return AugmentResult(
            augmented_xml,
            Metadata(
                original_eicr_id=self.original_eicr_id,
                augmented_eicr_id=CdaInstanceIdentifier(root=self.new_doc_id, extension=None),
                nonstandard_codes=nonstandard_code_metadata,
            ),
        )

    def _replace_element(self, xpath: str, new_element: Element) -> None:
        """Replace a child in the augmented document, preserving whitespace tail."""
        old = self._get_augmented_tag_by_xpath(xpath)
        new_element.tail = old.tail
        self._augmented_element.replace(old, new_element)

    def _handle_document_id_header(self) -> None:
        """Replace the document ID, effectiveTime, setId, and versionNumber in the augmented eICR."""
        self._replace_element("/ClinicalDocument/id", self._get_new_document_id())

        old_eff_time = self._get_augmented_tag_by_xpath("/ClinicalDocument/effectiveTime")
        self._add_previous_element_comment("time of data augmentation operation ", old_eff_time)
        self._replace_element("/ClinicalDocument/effectiveTime", self._get_new_effective_time())

        old_set_id = self._get_augmented_tag_by_xpath("/ClinicalDocument/setId")
        self._add_previous_element_comment("new-document-setId ", old_set_id)
        self._replace_element("/ClinicalDocument/setId", self._get_new_set_id())

        old_version = self._get_augmented_tag_by_xpath("/ClinicalDocument/versionNumber")
        self._add_previous_element_comment("new-document-versionNumber ", old_version)
        self._replace_element("/ClinicalDocument/versionNumber", self._get_new_version_number())

        new_id = self._get_augmented_tag_by_xpath("/ClinicalDocument/id")
        self._add_previous_element_comment("eICR Data Augmentation Header ", new_id)
        new_id.addprevious(self._get_augmented_template_id())
        self._add_previous_element_comment("new-document-id ", new_id)

    def _handle_related_document_header(self) -> None:
        """Add related document referencing the old eICR."""
        related_doc = cda_element("relatedDocument", self._augmented_element)
        related_doc.set("typeCode", "XFRM")
        self._add_previous_element_comment(" typeCode 'XFRM' ", related_doc)
        parent_doc = cda_element("parentDocument", related_doc)
        parent_doc_id = self._get_old_document_id()
        parent_doc.append(parent_doc_id)
        # comments need to be added to the element after it's been appended to the parent
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

    def _get_augmented_attribute_by_xpath(self, xpath: str) -> str:
        """Get attribute from the augmented eICR by XPath."""
        return self._get_attribute_by_xpath(self._augmented_element, xpath)

    def _get_optional_augmented_attribute_by_xpath(self, xpath: str) -> str | None:
        """Get attribute from the augmented eICR by XPath, or None if not found."""
        results = self._augmented_element.xpath(cda_xpath(xpath), namespaces=CDA_NSMAP)
        if not results:
            return None
        return str(results[0])

    def _get_element_by_xpath(self, element: Element, xpath: str) -> Element:
        """Get the first matching child element by XPath, or raise if not found."""
        results = element.xpath(cda_xpath(xpath), namespaces=CDA_NSMAP)
        if not results:
            raise ValueError(f"Unable to find tag in eICR document for XPath: {xpath}")
        return results[0]

    def _get_attribute_by_xpath(self, element: Element, xpath: str) -> str:
        """Get the first matching attribute by XPath, or raise if not found."""
        results = element.xpath(cda_xpath(xpath), namespaces=CDA_NSMAP)
        if not results:
            raise ValueError(f"Unable to find tag in eICR document for XPath: {xpath}")
        return str(results[0])

    def _get_old_document_id(self) -> Element:
        """Extract the parent document ID from original eICR document."""
        parent_doc_id = self._get_original_by_xpath("/ClinicalDocument/id")
        if parent_doc_id.get("assigningAuthorityName") is None:
            parent_doc_id.set("assigningAuthorityName", "original-document")
        return parent_doc_id

    def _get_old_set_id(self) -> Element:
        """Extract the parent document setId from original eICR document."""
        return self._get_original_by_xpath("/ClinicalDocument/setId")

    def _get_old_version_number(self) -> Element:
        """Extract the parent versionNumber from original eICR document."""
        return self._get_original_by_xpath("/ClinicalDocument/versionNumber")

    def _generate_deterministic_id(self, identifier_type: str) -> str:
        """Generate a stable UUID for augmented eICR identifiers."""
        return str(
            uuid5(
                NAMESPACE_URL,
                f"{_APPLICATION_CODE_VALUE}:{self.deterministic_id_seed}:{identifier_type}",
            )
        )

    def _get_new_document_id(self) -> Element:
        """Generate a new document ID element for the augmented eICR document."""
        doc_id_tag = cda_element("id")
        doc_id_tag.set("root", self.new_doc_id)
        doc_id_tag.set("assigningAuthorityName", _APPLICATION_CODE_VALUE)
        return doc_id_tag

    def _get_new_set_id(self) -> Element:
        """Generate a new setId element for the augmented eICR document."""
        set_id_tag = cda_element("setId")
        set_id_tag.set("root", self.new_set_id)
        return set_id_tag

    def _get_new_effective_time(self) -> Element:
        """Generate an effectiveTime element for the augmented eICR document."""
        effective_time_tag = cda_element("effectiveTime")
        effective_time_tag.set("value", self.augmentation_date.strftime("%Y%m%d%H%M%S"))
        return effective_time_tag

    def _get_new_version_number(self) -> Element:
        """Generate a new versionNumber element for the augmented eICR document."""
        old_version_number = self._get_old_version_number()
        version_number_tag = cda_element("versionNumber")
        version_number_tag.set("value", old_version_number.get("value", "1"))
        return version_number_tag

    def _get_augmented_template_id(self) -> Element:
        """Generate a new templateId element for the augmented eICR document."""
        # this new templateId is defined in the Augmentation Spec V2
        template_id_tag = cda_element("templateId")
        template_id_tag.set("root", "2.16.840.1.113883.10.20.15.2.1.3")
        template_id_tag.set("extension", "2025-11-01")
        return template_id_tag

    def _add_previous_element_comment(self, comment: str, element: Element) -> None:
        """Add an XML comment immediately before the given element."""
        element.addprevious(etree.Comment(f"DATA AUGMENTATION: {comment.strip()} "))

    def _generate_author(self, is_header: bool = True) -> Element:
        """Generate an author element for the augmented eICR document."""
        null_flavor_comment = " set to nullFlavor 'NA' "
        author = cda_element("author")
        if not is_header:
            function_code = cda_element("functionCode", author)
            function_code.set("code", value=_AUTHOR_FUNCTION_CODE)
            function_code.set("codeSystem", value=_AUTHOR_FUNCTION_CODE_SYSTEM)
            function_code.set("codeSystemName", value=_AUTHOR_FUNCTION_CODE_SYSTEM_NAME)
            self._add_previous_element_comment(
                f"functionCode specifies type of change '{_AUTHOR_FUNCTION_CODE}' which signifies that the code in this observation has been augmented with a code derived from the text in the code element ",
                function_code,
            )
        author_eff_time = self._get_new_effective_time()
        author.append(author_eff_time)
        self._add_previous_element_comment("time of data augmentation operation ", author_eff_time)
        if is_header:
            self._add_previous_element_comment(
                (
                    "Header-level Author to flag that this document "
                    "has been transformed on the platform (e.g. to add text-to-code information) "
                    "The functionCode holds the tool used/type of transform (e.g. text-to-code) "
                    "and the time holds the time of the transformation/operation "
                ),
                author,
            )
        assigned_author = cda_element("assignedAuthor", author)
        id = cda_element("id", assigned_author)
        id.set("nullFlavor", "NA")
        self._add_previous_element_comment(null_flavor_comment, id)
        addr = cda_element("addr", assigned_author)
        addr.set("nullFlavor", "NA")
        self._add_previous_element_comment(null_flavor_comment, addr)
        telecom = cda_element("telecom", assigned_author)
        telecom.set("nullFlavor", "NA")
        self._add_previous_element_comment(null_flavor_comment, telecom)
        assigned_authoring_device = cda_element("assignedAuthoringDevice", assigned_author)
        self._add_previous_element_comment(
            " set to 'Data Augmentation Tool' ", assigned_authoring_device
        )
        software_name = cda_element("softwareName", assigned_authoring_device)
        software_name.set("code", value=_APPLICATION_CODE_VALUE)
        software_name.set("codeSystem", value=_AUTHOR_FUNCTION_CODE_SYSTEM)
        software_name.set("codeSystemName", value=_AUTHOR_FUNCTION_CODE_SYSTEM_NAME)
        software_name.set("displayName", _APPLICATION_CODE_DISPLAY)
        self._add_previous_element_comment(
            " assignedAuthoringDevice/softwareName specifies that this document has been transformed using the Text-to-Code data augmentation tool",
            software_name,
        )
        return author

    def _handle_author_entry(self, augmentation: NonstandardCodeInstance) -> None:
        """Add an author entry for the given nonstandard code augmentation."""
        entry = self._get_augmented_tag_by_xpath(augmentation.schematron_error_xpath)
        entry.append(self._generate_author(is_header=False))

    # TODO: this will need to be modified in the future when we have
    # other data elements, other than observation.codes that are being augmented
    def _handle_translation(self, augmentation: NonstandardCodeInstance) -> str:
        """Add a translation element for the given nonstandard code augmentation."""
        entry_code = self._get_augmented_tag_by_xpath(augmentation.schematron_error_xpath + "/code")
        self._add_previous_element_comment(
            "This data has been augmented with a standard LOINC code", entry_code
        )
        self._add_previous_element_comment(
            "The data in the code and code/originalText data elements is the original data",
            entry_code,
        )
        new_translation = cda_element("translation", entry_code)
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
    """Set an attribute on an element if the value is not None.

    :param element: The XML element to set the attribute on.
    :param key: The attribute name.
    :param value: The attribute value. If None, the attribute will not be set.
    """
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
