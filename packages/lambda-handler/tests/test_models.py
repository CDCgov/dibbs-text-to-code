from aws_lambda_powertools.utilities.data_classes import SQSRecord

from lambda_handler.models.opensearch import S3Location


class TestS3Location:
    def test_from_sqs_record(self):
        expected_bucket = "expected_bucket"
        expected_key = "expected_key"
        record = SQSRecord(
            {
                "body": f'{{"detail": {{"bucket": {{"name": "{expected_bucket}"}}}},"object": {{"key": "{expected_key}"}}}}'
            }
        )

        actual = S3Location.from_sqs_record(record)

        assert actual == S3Location(bucket=expected_bucket, key=expected_key)

    def test_address(self):
        test_bucket = "test_bucket"
        test_key = "test_key"
        expected_address = f"s3://{test_bucket}/{test_key}"

        location = S3Location(bucket=test_bucket, key=test_key)

        actual = location.address

        assert actual == expected_address
