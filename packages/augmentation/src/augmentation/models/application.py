from shared_models import (
    CdaInstanceIdentifier,
    FrozenBaseModel,
    NonstandardCodeInstance,
    PassthroughReason,
)


class NonstandardCodeInstanceMetadata(NonstandardCodeInstance):
    """Model for the metadata for each instance of a nonstandard code.

    This is the same as the `NonstandardCodeInstance` model, but includes the path to the new translation.
    """

    new_translation_xpath: str
    """XPath to the translation added to the augmented eICR with the standard code."""


class Metadata(FrozenBaseModel):
    """Model to hold augmentation metadata."""

    original_eicr_id: CdaInstanceIdentifier
    augmented_eicr_id: CdaInstanceIdentifier
    nonstandard_codes: list[NonstandardCodeInstanceMetadata]
    """List of the nonstandard codes TTC attempted to resolve."""
    error: str | None = None
    passthrough_reason: PassthroughReason | None = None


class TTCAugmenterOutput(FrozenBaseModel):
    """Output of the augmentation service."""

    persistence_id: str
    augmented_eicr: str
    metadata: Metadata
