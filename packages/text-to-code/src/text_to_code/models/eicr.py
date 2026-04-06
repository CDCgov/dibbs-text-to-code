from datetime import UTC
from datetime import datetime

from pydantic import BaseModel
from pydantic import ConfigDict

from shared_models import EICRMetadata
from shared_models import SchematronErrorDetail


class TTCMetadata(BaseModel):
    """Model to hold metadata about the TTC process."""

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )
    persistance_id: str
    message: str | None
    eicr_metadata: EICRMetadata | None
    schematron_errors: list[SchematronErrorDetail]
    processed_at: datetime = datetime.now(UTC)
