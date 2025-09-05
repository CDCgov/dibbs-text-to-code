import os
import random

import boto3
import moto
import pytest


@pytest.fixture(scope="function")
def moto_setup(monkeypatch):
    with moto.mock_aws():
        monkeypatch.setenv("AWS_REGION", "us-east-1")
        monkeypatch.setenv("AWS_ACCESS_KEY_ID", "test")
        monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "test")
        bucket_name = "test-bucket"

        # Create the fake S3 bucket
        s3 = boto3.client(
            "s3",
            region_name=os.environ["AWS_REGION"],
            aws_access_key_id=os.environ["AWS_ACCESS_KEY_ID"],
            aws_secret_access_key=os.environ["AWS_SECRET_ACCESS_KEY"],
        )
        s3.create_bucket(Bucket=bucket_name)

        # Add convenience attribute for tests
        s3.bucket_name = bucket_name

        yield s3


@pytest.fixture(autouse=True)
def fixed_random_seed():
    random.seed(42)
