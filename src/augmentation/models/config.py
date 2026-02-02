from pydantic import BaseModel
from pydantic import ConfigDict
from pydantic import model_validator

from .application import ApplicationCode
from .document import DocumentType


class AugmentorConfig(BaseModel):
    """Basic configuration controlling augmentation behavior."""

    # TODO: this is very much a shell and can be modified
    #  in the ticket related to creating an augmentor config model
    #  and retrieving said config from S3 Bucket

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    application_code: ApplicationCode
    document_type: DocumentType
    rules: dict


class TTCAugmentorConfig(AugmentorConfig):
    """Configuration for TTC augmentation behavior."""

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    application_code: ApplicationCode.TEXT_TO_CODE
    # for now we will hardcode this to eICR since TTC only
    #  deals with eICR documents at this point
    document_type: DocumentType.EICR
    # TODO:
    # this is just an example of what the rules for eICR augmentation might look like
    # typically we should expect these to come from the configuration in S3
    rules: dict = {
        "lab_test_name_resulted": [
            "document_id_header",
            "author_header",
            "author_entry",
            "translation",
        ]
    }

    @model_validator(mode="after")
    def validate_rules(self) -> "TTCAugmentorConfig":
        """Ensures that there are rules defined for augmentation."""
        if not self.rules or len(self.rules) == 0:
            raise ValueError("rules must contain at least one augmentation rule!")
        return self
