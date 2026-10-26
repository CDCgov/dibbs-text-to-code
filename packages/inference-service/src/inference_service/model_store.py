import logging
import os
import re
from pathlib import Path
from urllib.parse import urlparse

import boto3
from huggingface_hub import snapshot_download

logger = logging.getLogger(__name__)

# Hugging Face download bookkeeping that is sometimes copied up alongside the weights.
_SKIPPED_DIRS = {".cache"}


def resolve_model(uri: str, cache_dir: Path) -> Path:
    """Makes a model available on local disk and returns its directory.

    This is how models are swapped without rebuilding the image: the service loads
    whatever the URI points to at startup.

    Args:
        uri: An ``s3://bucket/prefix/`` holding a saved sentence-transformers model, an
            existing local directory, or a Hugging Face repo id.
        cache_dir: Directory that remote models are downloaded into.

    Returns:
        The local directory containing the model.
    """
    if os.path.isdir(uri):
        logger.info("Loading model from local directory %s", uri)
        return Path(uri)

    dest = cache_dir / _safe_dir_name(uri)
    if uri.startswith("s3://"):
        _download_s3_prefix(uri, dest)
        return dest

    logger.info("Downloading model %s from Hugging Face to %s", uri, dest)
    return Path(snapshot_download(repo_id=uri, local_dir=dest))


def _download_s3_prefix(uri: str, dest: Path) -> None:
    parsed = urlparse(uri)
    bucket = parsed.netloc
    prefix = parsed.path.lstrip("/")
    if prefix and not prefix.endswith("/"):
        prefix += "/"

    s3 = boto3.client("s3")
    paginator = s3.get_paginator("list_objects_v2")
    count = 0
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        for obj in page.get("Contents", []):
            key = obj["Key"]
            relative = key.removeprefix(prefix)
            if not relative or key.endswith("/"):
                continue
            if _SKIPPED_DIRS.intersection(Path(relative).parts):
                continue
            target = dest / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            s3.download_file(bucket, key, str(target))
            count += 1

    if count == 0:
        raise FileNotFoundError(f"No model files found at {uri}")
    logger.info("Downloaded %d model files from %s to %s", count, uri, dest)


def _safe_dir_name(uri: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "--", uri).strip("-")
