from shared_models import TTCAugmenterInput

from augmentation.models import Metadata
from augmentation.models import TTCAugmenterConfig
from augmentation.services.eicr_augmenter import EICRAugmenter


def _retrieve_eicr(eicr_id: str) -> str:
    return eicr_id


def _retrieve_config() -> TTCAugmenterConfig:
    return TTCAugmenterConfig()


def _save_eicr(eicr: str) -> None:
    """Save augmented eICR to S3 bucket."""
    pass


def _save_metadata(metadata: Metadata) -> None:
    """Save augmentation metadata to S3 bucket."""
    pass


def augment(input: TTCAugmenterInput) -> str:
    """Main entry point for the augmentation service."""
    eicr: str = _retrieve_eicr(input.eicr)
    config = _retrieve_config()
    augmenter = EICRAugmenter(eicr, input.augmentations, config)

    metadata = Metadata(original_eicr_id=input.eicr, augmented_eicr_id=augmenter.new_doc_id)

    _save_eicr(augmenter.augmented_xml)
    _save_metadata(metadata)

    return augmenter.augmented_xml
