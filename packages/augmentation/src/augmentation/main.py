"""I don't think we want this to be in `main.py` but I'm not 100% sure how this will get plumbed with AWS, so this is as good as anywhere for the moment."""

import os
from io import BytesIO

from augmentation.models import Metadata
from augmentation.models import TTCAugmenterConfig
from augmentation.services.eicr_augmenter import EICRAugmenter
from lambda_handler.lambda_handler import put_file
from shared_models import TTCAugmenterInput

S3_BUCKET = os.getenv("S3_BUCKET", "dibbs-text-to-code")
AUGMENTED_EICR_PREFIX = os.getenv("AUGMENTED_EICR_PREFIX", "AugmentationEICRV2/")
AUGMENTATION_METADATA_PREFIX = os.getenv("AUGMENTATION_METADATA_PREFIX", "AugmentationMetadata/")


def _retrieve_eicr(eicr_id: str) -> str:
    return "<ClinicalDocument></ClinicalDocument>"


def _retrieve_config() -> TTCAugmenterConfig:
    return TTCAugmenterConfig()


def _save_eicr(eicr: str, eicr_id: str) -> None:
    """Save augmented eICR to S3 bucket."""
    put_file(BytesIO(eicr.encode("utf-8")), S3_BUCKET, f"{AUGMENTED_EICR_PREFIX}{eicr_id}")


def _save_metadata(metadata: Metadata) -> None:
    """Save augmentation metadata to S3 bucket."""
    put_file(
        BytesIO(metadata.model_dump_json().encode("utf-8")),
        S3_BUCKET,
        f"{AUGMENTATION_METADATA_PREFIX}{metadata.augmented_eicr_id}",
    )


def augment(input: TTCAugmenterInput) -> None:
    """Main entry point for the augmentation service."""
    eicr: str = _retrieve_eicr(input.eicr_id)
    config = _retrieve_config()
    augmenter = EICRAugmenter(eicr, input.nonstandard_codes, config)

    metadata = augmenter.augment()

    _save_eicr(augmenter.augmented_xml, input.eicr_id)
    _save_metadata(metadata)
