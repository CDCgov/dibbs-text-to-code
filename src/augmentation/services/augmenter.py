from datetime import datetime
from functools import cached_property

from lxml.etree import Element
from pydantic import BaseModel
from pydantic import Field
from pydantic import field_validator

from ..models.application import ApplicationCode
from ..models.config import AugmenterConfig
from ..models.config import TTCAugmenterConfig
from .eicr_utils import clean_xml_tree


class Augmenter(BaseModel):
    """Augments a document (e.g., eICR) with additional information using a validated config."""

    application_code: ApplicationCode = Field(
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
        # where the implementation will fleshed out in the subclasses
        return self.document_payload

    def _validate_config(self) -> None:
        """Validates that the config matches the application and document type."""
        if self.config.application_code != self.application_code:
            raise ValueError(
                f"Config application code {self.config.application_code} does not match Augmenter application code {self.application_code}."
            )
        if self.config.rules is None or len(self.config.rules) == 0:
            raise ValueError("Config must contain at least one augmentation rule!")


class TTCAugmenter(Augmenter):
    """Augmenter specific to TTC eICR documents.

    If document_data is provided and it's a TTC Augmenter,
    then we expect that it should be an eICR document and
    set that in the class attribute accordingly
    """

    application_code: ApplicationCode = ApplicationCode.TEXT_TO_CODE

    # TODO: for now just use hard coded TTC Config
    #  we will need to remove/change this once we have S3 config integrated
    config: AugmenterConfig = TTCAugmenterConfig()

    @cached_property
    def eicr_base(self) -> Element:
        """CLeaned and parsed document_payload into an XML Element."""
        return clean_xml_tree(self.document_payload)

    def _get_by_xpath(self, xpath: str) -> Element | None:
        if self.eicr_base is None:
            return None
        return self.eicr_base.xpath(xpath)
