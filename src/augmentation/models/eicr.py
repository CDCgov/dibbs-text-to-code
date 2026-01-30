from enum import StrEnum


class ECRDataField(StrEnum):
    """Enum for eICR data fields augmentation can modify."""

    LAB_TEST_NAME_RESULTED = "Lab Test Name Resulted"
    LAB_TEST_NAME_ORDERED = "Lab Test Name Ordered"
