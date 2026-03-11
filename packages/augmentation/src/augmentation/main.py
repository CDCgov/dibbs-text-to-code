"""I don't think we want this to be in `main.py` but I'm not 100% sure how this will get plumbed with AWS, so this is as good as anywhere for the moment."""

from io import BytesIO

from lambda_handler.lambda_handler import put_file
from shared_models import TTCAugmenterInput

from augmentation.models import Metadata
from augmentation.models import TTCAugmenterConfig
from augmentation.services.eicr_augmenter import EICRAugmenter


def _retrieve_eicr(eicr_id: str) -> str:
    return "<ClinicalDocument></ClinicalDocument>"


def _retrieve_config() -> TTCAugmenterConfig:
    return TTCAugmenterConfig()


def _save_eicr(eicr: str, eicr_id: str) -> None:
    """Save augmented eICR to S3 bucket."""
    put_file(BytesIO(eicr.encode("utf-8")), "augmented_eicrs", eicr_id)


def _save_metadata(metadata: Metadata) -> None:
    """Save augmentation metadata to S3 bucket."""
    put_file(
        BytesIO(metadata.model_dump_json().encode("utf-8")),
        "augmentation_metadata",
        f"{metadata.augmented_eicr_id}_metadata.json",
    )


def augment(input: TTCAugmenterInput) -> None:
    """Main entry point for the augmentation service."""
    eicr: str = _retrieve_eicr(input.eicr_id)
    config = _retrieve_config()
    augmenter = EICRAugmenter(eicr, input.nonstandard_codes, config)

    metadata = augmenter.augment()

    _save_eicr(augmenter.augmented_xml, input.eicr_id)
    _save_metadata(metadata)
