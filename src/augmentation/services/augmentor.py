from datetime import datetime
from xml.etree.ElementTree import Element

from lxml import etree
from pydantic import BaseModel
from pydantic import ConfigDict
from pydantic import Field
from pydantic import field_validator
from pydantic import model_validator

from ..models.application import ApplicationCode
from ..models.eicr import DataField
from .eicr_utils import clean_xml_tree


class Augmentor(BaseModel):
    """Augment a document (e.g., eICR) with additional information."""

    application_code: ApplicationCode = Field(
        default=ApplicationCode.TEXT_TO_CODE,
        description="The application requesting augmenation of a document.",
    )

    @field_validator("document_data", mode="before")
    @classmethod
    def document_data_not_none(cls, v: str) -> str:  # noqa: D102
        if v is None or v.strip() == "":
            raise ValueError("Document data must be be a non-empty string!")
        return v

    document_data: str = Field(
        description="The data of the document to be augmented (ie. eICR, etc...)."
    )

    augmented_document: str | None = Field(
        default=None, description="The augmented document data after processing."
    )

    augmented_date: datetime = Field(
        default=datetime.now(), description="The date and time when the document was augmented."
    )

    data_fields: list[DataField] | None = Field(
        default=None, description="The data fields relevant to the document being augmented."
    )

    @field_validator("data_config", mode="before")
    @classmethod
    def data_config_not_none(cls, v: str) -> str:  # noqa: D102
        if v is None or v == {}:
            raise ValueError("Data configuration must be supplied for augmentation!")
        return v

    data_config: dict = Field(
        description="The configuration that provides the rules for augmentation by application and data element.",
    )

    def _get_application(self) -> ApplicationCode:
        return self.application_code

    def _get_application_code_value(self) -> str:
        return self.application_code.value


class TTCAugmentor(Augmentor):
    """Augmentor specific to TTC eICR documents."""

    # required to allow etree._Element type for eicr_base below
    model_config = ConfigDict(arbitrary_types_allowed=True)

    application_code: ApplicationCode = ApplicationCode.TEXT_TO_CODE
    data_fields: list[DataField] = [
        DataField.LAB_TEST_NAME_RESULTED,
        DataField.LAB_TEST_NAME_ORDERED,
    ]

    # if document_data is provided and it's a
    # TTC augmentor, then we expect that it should
    # be an eICR document and set that in the class attribute accordingly
    @model_validator(mode="after")
    def set_eicr_base(self) -> "TTCAugmentor":
        """Cleans and sets up the base XML element for eICR processing."""
        self.eicr_base: etree._Element = clean_xml_tree(self.document_data)
        return self

    eicr_base: etree._Element | None = Field(
        default=None, description="The base XML element of the eICR document after cleaning."
    )

    def _get_by_xpath(self, xpath: str) -> Element:
        return self.eicr_base.xpath(xpath)
