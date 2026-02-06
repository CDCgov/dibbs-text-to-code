import copy
from datetime import datetime
from functools import cached_property
from uuid import uuid4

from lxml import etree
from lxml.etree import Element
from pydantic import BaseModel
from pydantic import ConfigDict
from pydantic import Field
from pydantic import field_validator

from ..models.application import ApplicationCode
from ..models.config import AugmenterConfig
from ..models.config import TTCAugmenterConfig
from ..models.eicr import DataField
from .eicr_utils import clean_xml_tree


class Augmenter(BaseModel):
    """Augments a document (e.g., eICR) with additional information using a validated config."""

    application_code: ApplicationCode = Field(
        default=ApplicationCode.TEXT_TO_CODE,
        description="The application requesting augmenation of a document.",
    )

    @field_validator("document_payload", mode="before")
    @classmethod
    def document_payload_not_none(cls, v: str) -> str:
        """Validates that the document payload is always supplied as a non-empty string."""
        if v is None or v.strip() == "":
            raise ValueError("Document payload must be a non-empty string!")
        return v

    document_payload: str = Field(
        description="The data of the document to be augmented (ie. eICR, etc...)."
    )

    augmented_document: str | None = Field(
        default=None, description="The augmented document data after processing."
    )

    augmented_date: datetime = Field(
        default_factory=datetime.now,
        description="The date and time when the document was augmented, defaults to current local time.",
    )

    @field_validator("config", mode="before")
    @classmethod
    def config_not_none(cls, v: str) -> str:
        """Validates that the config is always supplied."""
        if v is None or v == {}:
            raise ValueError("Augmentation configuration must be supplied!")
        return v

    config: AugmenterConfig = Field(
        description="The validated configuration that provides the rules for augmentation by application and document type.",
    )

    def _get_application_code_value(self) -> str:
        return self.application_code.value

    def run(self) -> str:
        """Execute augmentation process on the document payload."""
        # This is a placeholder for the actual augmentation logic.
        self._validate_config()
        self.augmented_document = self._augment()  # No actual augmentation done here YET.
        return self.augmented_document

    def _augment(self) -> str:
        """Internal method to perform augmentation logic."""
        # this function is basically an interface
        # where the implementation will be fleshed out in the subclasses
        return self.document_payload

    def _validate_config(self) -> None:
        """Validates that the config matches the application and document type."""
        if self.config.application_code != self.application_code:
            raise ValueError(
                f"Config application code {self.config.application_code} does not match Augmenter application code {self.application_code}."
            )
        if self.config.rules is None or len(self.config.rules) == 0:
            raise ValueError("Config must contain at least one augmentation rule!")


class EICRAugmenter(Augmenter):
    """Augmenter specific to eICR documents.

    It is expected that the document payload will be
    an eICR document and therefore the class should
    automatically set various attributes specific to eICRs.
    """

    # for now only TTC is supported in Augmentation
    # and the only document type for TTC is eICR
    application_code: ApplicationCode = ApplicationCode.TEXT_TO_CODE

    # TODO: for now just use hard coded TTC Config
    #  we will need to remove/change this once we have S3 config integrated
    config: AugmenterConfig = TTCAugmenterConfig()

    new_doc_id: str = str(uuid4())
    new_set_id: str = str(uuid4())

    @cached_property
    def original_eicr(self) -> Element:
        """CLeaned and parsed document_payload into an XML Element."""
        return clean_xml_tree(self.document_payload)

    model_config = ConfigDict(arbitrary_types_allowed=True)

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
        # TODO: hard coding this to use the Lab Test Name Ordered rules for now
        # from the config, but we will need to use the input from TTC and
        # the config to determine what to actually augment - the
        # Output from TTC should contain (along with an eicr ID or full eicr)
        # a dataField: Full XPath to where the problem data element is located in the eicr
        ecr_data_field = DataField.LAB_TEST_NAME_ORDERED
        for rule in self.config.rules[ecr_data_field]:
            if rule == "document_id_header":
                self._handle_document_id_header()
        return etree.tostring(self.augmented_eicr).decode("utf-8")

    def _handle_document_id_header(self) -> None:
        # first replace the id tag
        old_id_element = self._get_augmented_tag_by_xpath("/ClinicalDocument/id")
        self.augmented_eicr.replace(old_id_element, self._get_new_document_id())

        # replace the effectiveTime tag
        old_eff_time_element = self._get_augmented_tag_by_xpath("/ClinicalDocument/effectiveTime")
        self.augmented_eicr.replace(old_eff_time_element, self._get_new_effective_time())
        # next replace the setId tag if
        old_set_id_element = self._get_augmented_tag_by_xpath("/ClinicalDocument/setId")
        self.augmented_eicr.replace(old_set_id_element, self._get_new_set_id())
        # finally replace the versionNumber tag
        old_version_element = self._get_augmented_tag_by_xpath("/ClinicalDocument/versionNumber")
        self.augmented_eicr.replace(old_version_element, self._get_new_version_number())

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

    def _get_parent_document_id(self) -> Element:
        """Extract the parent document ID from original eICR document."""
        doc_id_elements = self._get_original_by_xpath("/ClinicalDocument/id")
        if not doc_id_elements or len(doc_id_elements) == 0:
            raise ValueError("No document ID found in eICR document.")
        parent_doc_id = doc_id_elements[0]
        parent_doc_id.set("assigningAuthorityName", "original-document")
        # TODO:  Note that the namespaces will be present in the id tag
        #  do we need to remove them or leave them?
        return parent_doc_id

    def _get_parent_set_id(self) -> Element:
        """Extract the parent document setId from original eICR document."""
        set_id_elements = self._get_original_by_xpath("/ClinicalDocument/setId")
        if not set_id_elements or len(set_id_elements) == 0:
            raise ValueError("No document setId found in eICR document.")
        parent_set_id = set_id_elements[0]
        # TODO:  Note that the namespaces will be present in the setId tag
        #  do we need to remove them or leave them?
        return parent_set_id

    def _get_parent_version_number(self) -> Element:
        """Extract the parent versionNumber from original eICR document."""
        version_elements = self._get_original_by_xpath("/ClinicalDocument/versionNumber")
        if not version_elements or len(version_elements) == 0:
            raise ValueError("No document versionNumber found in eICR document.")
        version = version_elements[0]
        # TODO:  Note that the namespaces will be present in the versionNumber tag
        #  do we need to remove them or leave them?
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
        effective_time_tag.set("value", self.augmented_date.strftime("%Y%m%d%H%M%S"))
        return effective_time_tag

    def _get_new_version_number(self) -> Element:
        """Generate a versionNumber element for the augmented eICR document."""
        version_number_tag = etree.Element("versionNumber")
        # hard code to 1 for now
        # TODO: we may need to have some way to increment this later
        version_number_tag.set("value", "1")
        return version_number_tag
