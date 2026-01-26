from enum import StrEnum


class ApplicationCode(StrEnum):
    """The list of applications that will leveraging Augmentation functionality."""

    TEXT_TO_CODE = "text-to-code"
    ECR_REFINER = "ecr-refinement"
    QUERY_CONNECTOR = "additional-context-data"
