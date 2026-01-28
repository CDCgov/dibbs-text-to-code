from datetime import datetime

from lxml import etree
from lxml.etree import Element
from pydantic import BaseModel
from pydantic import Field
from pydantic import field_validator

from augmentation.models.application import ApplicationCode
from augmentation.models.eicr import ECRDataField


class Augmentor(BaseModel):
    """Augment a document (e.g., eICR) with additional information."""

    _application_code: ApplicationCode = Field(
        description="The application requesting augmenation of a document."
    )

    @field_validator("_document_data", mode="before")
    @classmethod
    def document_data_not_none(cls, v: str) -> str:  # noqa: D102
        if v is None or v.strip() == "":
            raise ValueError("document_data must be a non-empty string")
        return v

    _document_data: str = Field(
        description="The data of the document to be augmented (ie. eICR, etc...)."
    )

    _augmented_document: str | None = Field(
        default=None, description="The augmented document data after processing."
    )

    _augmented_date: datetime = Field(
        default=datetime.now(), description="The date and time when the document was augmented."
    )

    _data_fields: list[ECRDataField] | None = Field(
        default=None, description="The data fields relevant to the document being augmented."
    )

    @field_validator("_data_config", mode="before")
    @classmethod
    def data_config_not_none(cls, v: str) -> str:  # noqa: D102
        if v is None or v == {}:
            raise ValueError("Data configuration must be supplied for augmentation!")
        return v

    _data_config: dict | None = Field(
        description="The configuration that provides the rules for augmentation by application and data element.",
    )

    def _getapplication(self) -> ApplicationCode:
        return self._application_code


class TTCAugmentor(Augmentor):
    """Augmentor specific to TTC eICR documents."""

    _application_code = ApplicationCode.TEXT_TO_CODE
    _data_fields: list[ECRDataField] = [
        ECRDataField.LAB_TEST_NAME_RESULTED,
        ECRDataField.LAB_TEST_NAME_ORDERED,
    ]

    def clean_xml_tree() -> Element:
        """Remove all namespaces from an XML tree."""
        tree = etree.fromstring(Augmentor._document_data.encode("utf-8"))
        for elem in tree.iter():
            # Remove namespace from tag
            elem.tag = etree.QName(elem).localname
        # Remove namespace declarations
        etree.cleanup_namespaces(tree)
        return tree

    _eicr_base = clean_xml_tree()

    def _get_by_xpath(self, xpath: str) -> Element:
        return self._xml_root.xpath(xpath)
