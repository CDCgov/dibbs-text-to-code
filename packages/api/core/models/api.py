from dataclasses import dataclass
from typing import Literal


# response models
@dataclass(frozen=True)
class StatusResponse:
    """Health check response."""

    status: Literal["OK"]
