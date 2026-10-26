import boto3
import moto
import pytest

from inference_service import model_store
from inference_service.model_store import resolve_model

BUCKET = "models-bucket"


@pytest.fixture
def s3():
    with moto.mock_aws():
        client = boto3.client("s3", region_name="us-east-1")
        client.create_bucket(Bucket=BUCKET)
        yield client


def test_downloads_s3_prefix_and_skips_hf_cache(s3, tmp_path):
    for key in (
        "models/retriever/config.json",
        "models/retriever/model.safetensors",
        "models/retriever/1_Pooling/config.json",
        "models/retriever/.cache/huggingface/download/model.safetensors.metadata",
        "models/retriever-v2/config.json",
    ):
        s3.put_object(Bucket=BUCKET, Key=key, Body=b"{}")

    path = resolve_model(f"s3://{BUCKET}/models/retriever", tmp_path)

    files = sorted(str(p.relative_to(path)) for p in path.rglob("*") if p.is_file())
    assert files == ["1_Pooling/config.json", "config.json", "model.safetensors"]


def test_missing_s3_prefix_raises(s3, tmp_path):
    with pytest.raises(FileNotFoundError, match="No model files"):
        resolve_model(f"s3://{BUCKET}/models/missing/", tmp_path)


def test_local_directory_is_used_in_place(tmp_path):
    assert resolve_model(str(tmp_path), tmp_path / "cache") == tmp_path


def test_other_uris_download_from_hugging_face(mocker, tmp_path):
    download = mocker.patch.object(model_store, "snapshot_download", return_value="/hf/model")

    path = resolve_model("NCHS/ttc-reranker-v1.0", tmp_path)

    assert str(path) == "/hf/model"
    download.assert_called_once_with(
        repo_id="NCHS/ttc-reranker-v1.0", local_dir=tmp_path / "NCHS--ttc-reranker-v1.0"
    )
