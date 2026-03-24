from pydantic import BaseModel
from pydantic import ConfigDict
from pydantic import model_validator

from shared_models import DataField

from .application import ApplicationCode
from .document import DocumentType


class AugmenterConfig(BaseModel):
    """Basic configuration controlling augmentation behavior."""

    # TODO: this is very much a shell and can be modified
    #  in the ticket related to creating an Augmenter config model
    #  and retrieving said config from S3 Bucket

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    application_code: ApplicationCode
    document_type: DocumentType
    rules: dict


class TTCAugmenterConfig(AugmenterConfig):
    """Configuration for TTC augmentation behavior."""

    application_code: ApplicationCode = ApplicationCode.TEXT_TO_CODE
    # for now we will hardcode this to eICR since TTC only
    #  deals with eICR documents at this point
    document_type: DocumentType = DocumentType.EICR
    # TODO:
    # this is just an example of what the rules for eICR augmentation might look like
    # typically we should expect these to come from the configuration in S3
    rules: dict = {
        "document": [
            "document_id_header",
            "author_header",
        ],
        DataField.LAB_TEST_NAME_ORDERED: [
            "author_entry",
            "translation",
        ],
        DataField.LAB_TEST_NAME_RESULTED: [
            "author_entry",
            "translation",
        ],
    }
    # TODO: The function code is currently a constant (used for both lab orders and results), but will need to be dynamic when additional fields with different function codes are introduced.
    author_function_code: str = "code-text-to-code"
    author_function_code_system: str = "2.16.840.1.113883.10.20.15.2.7.1"
    author_function_code_system_name: str = "eCRDataAugmentation"

    @model_validator(mode="after")
    def validate_rules(self) -> "TTCAugmenterConfig":
        """Ensures that there are rules defined for augmentation."""
        if not self.rules or len(self.rules) == 0:
            raise ValueError("Configuration rules must contain at least one augmentation rule!")
        return self
