from augmentation.models import TTCAugmenterConfig
from augmentation.models import TTCAugmenterInput
from augmentation.services.eicr_augmenter import EICRAugmenter


def _retrieve_eicr(eicr_id: str) -> str:
    return "<ClinicalDocument></ClinicalDocument>"


def _retrieve_config() -> TTCAugmenterConfig:
    return TTCAugmenterConfig()


def augment(input: TTCAugmenterInput) -> None:
    """Main entry point for the augmentation service."""
    eicr = _retrieve_eicr(input.eicr_id)
    config = _retrieve_config()
    EICRAugmenter(eicr, input.augmentations, config)
