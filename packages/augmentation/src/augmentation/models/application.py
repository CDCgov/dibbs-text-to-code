from enum import StrEnum

from pydantic import BaseModel
from shared_models import DataField


class ApplicationCode(StrEnum):
    """The list of applications that will leveraging Augmentation functionality."""

    TEXT_TO_CODE = "text-to-code"


class Candidate(BaseModel):
    """Model of the metadata for the nonstandard code candidates."""

    value: str
    """String value of candidate."""
    xpath: str
    """XPath to the candidate value in the original eICR."""
    selected: bool
    """Was this the selected candidate?"""


class NonstandardCodeInstance(BaseModel):
    """Model to hold metadata related to each Schematron error relevant TTC attempted to resolve. Specifically these are instances of nonstandard codes."""

    schematron_error: str
    """The text of the Schematron error."""
    schematron_error_xpath: str
    """The XPath give by the Schematron error to the observation with a nonconforming code."""
    field_type: DataField
    """The `DataField` type of the nonconforming code."""
    nonstandard_code_candidates: list[Candidate]
    """List of the possible candidates to use in the Opensearch query."""
    new_translation_xpath: str
    """XPath to the translation added to the augmented eICR with the standard code."""


class Metadata(BaseModel):
    """Model to hold augmentation metadata."""

    original_eicr_id: str
    augmented_eicr_id: str
    nonstandard_codes: list[NonstandardCodeInstance]
    """List of the nonstandard codes TTC attempted to resolve."""
    error: str
