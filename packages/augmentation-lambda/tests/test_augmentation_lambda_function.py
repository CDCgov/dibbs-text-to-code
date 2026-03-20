import json

from augmentation_lambda import lambda_function
from shared_models import TTCAugmenterInput

from augmentation.models import Metadata


class FakeAugmenter:
    def __init__(self, document: str, nonstandard_codes: list[object], config: object) -> None:
        """Fake augmenter for testing purposes.

        :param document: The input document to augment.
        :param nonstandard_codes: The list of nonstandard codes to resolve.
        :param config: The augmenter config to use for augmentation.
        """
        self.document = document
        self.nonstandard_codes = nonstandard_codes
        self.config = config
        self.augmented_xml = '<ClinicalDocument><id root="augmented-doc-id" /></ClinicalDocument>'

    def augment(self) -> Metadata:
        """Fake augment method that returns a successful augmentation result.

        :return: A Metadata object representing the result of the augmentation.
        """
        return Metadata(
            original_eicr_id="original-doc-id",
            augmented_eicr_id="augmented-doc-id",
            nonstandard_codes=[],
        )


def test_handler_returns_success_result(mocker) -> None:
    """Tests that the handler returns a successful result when the augmenter runs without errors.

    :param mocker: The pytest-mock fixture for mocking objects.
    """
    mocker.patch.object(lambda_function, "EICRAugmenter", FakeAugmenter)

    model_validate_spy = mocker.spy(TTCAugmenterInput, "model_validate")

    event = {
        "Records": [
            {
                "messageId": "message-1",
                "body": json.dumps(
                    {
                        "eicr_id": "source-eicr-id",
                        "eicr": "<ClinicalDocument />",
                        "nonstandard_codes": [],
                    }
                ),
            }
        ]
    }

    result = lambda_function.handler(event, None)

    assert model_validate_spy.call_count == 1
    assert model_validate_spy.call_args.args[0] == {
        "eicr_id": "source-eicr-id",
        "nonstandard_codes": [],
    }
    assert result == {
        "results": [
            {
                "messageId": "message-1",
                "status": "success",
                "result": {
                    "augmented_eicr": '<ClinicalDocument><id root="augmented-doc-id" /></ClinicalDocument>',
                    "metadata": {
                        "original_eicr_id": "original-doc-id",
                        "augmented_eicr_id": "augmented-doc-id",
                        "nonstandard_codes": [],
                        "error": None,
                    },
                },
            }
        ],
        "batchItemFailures": [],
    }


def test_handler_uses_provided_config(mocker) -> None:
    """Tests that the handler uses the provided config when creating the augmenter.

    :param mocker: The pytest-mock fixture for mocking objects.
    """
    augmenter_mock = mocker.patch.object(lambda_function, "EICRAugmenter", autospec=True)
    augmenter_instance = augmenter_mock.return_value
    augmenter_instance.augment.return_value = Metadata(
        original_eicr_id="original-doc-id",
        augmented_eicr_id="augmented-doc-id",
        nonstandard_codes=[],
    )
    augmenter_instance.augmented_xml = (
        '<ClinicalDocument><id root="augmented-doc-id" /></ClinicalDocument>'
    )

    config_validate_spy = mocker.spy(lambda_function.TTCAugmenterConfig, "model_validate")

    event = {
        "Records": [
            {
                "messageId": "message-2",
                "body": json.dumps(
                    {
                        "eicr_id": "source-eicr-id",
                        "eicr": "<ClinicalDocument />",
                        "nonstandard_codes": [],
                        "config": {
                            "rules": {
                                "document": [
                                    "document_id_header",
                                    "author_header",
                                ]
                            }
                        },
                    }
                ),
            }
        ]
    }

    result = lambda_function.handler(event, None)

    assert config_validate_spy.call_count == 1
    augmenter_mock.assert_called_once()
    assert augmenter_mock.call_args.kwargs["document"] == "<ClinicalDocument />"
    assert augmenter_mock.call_args.kwargs["config"] == config_validate_spy.spy_return
    assert result["batchItemFailures"] == []
    assert result["results"][0]["status"] == "success"


def test_handler_returns_error_for_invalid_payload(mocker) -> None:
    """Tests that the handler returns an error result for an invalid payload.

    :param mocker: The pytest-mock fixture for mocking objects.
    """
    mocker.patch.object(lambda_function, "EICRAugmenter", FakeAugmenter)

    event = {
        "Records": [
            {
                "messageId": "message-3",
                "body": json.dumps(
                    {
                        "eicr": "<ClinicalDocument />",
                        "nonstandard_codes": [],
                    }
                ),
            }
        ]
    }

    result = lambda_function.handler(event, None)

    assert result["batchItemFailures"] == [{"itemIdentifier": "message-3"}]
    assert result["results"][0]["messageId"] == "message-3"
    assert result["results"][0]["status"] == "error"


def test_handler_returns_error_when_augmenter_raises(mocker) -> None:
    """Tests that the handler returns an error result when the augmenter raises an exception.

    :param mocker: The pytest-mock fixture for mocking objects.
    """

    class RaisingAugmenter:
        def __init__(self, document: str, nonstandard_codes: list[object], config: object):
            self.document = document
            self.nonstandard_codes = nonstandard_codes
            self.config = config

        def augment(self) -> Metadata:
            raise ValueError("augmentation failed")

    mocker.patch.object(lambda_function, "EICRAugmenter", RaisingAugmenter)

    event = {
        "Records": [
            {
                "messageId": "message-4",
                "body": json.dumps(
                    {
                        "eicr_id": "source-eicr-id",
                        "eicr": "<ClinicalDocument />",
                        "nonstandard_codes": [],
                    }
                ),
            }
        ]
    }

    result = lambda_function.handler(event, None)

    assert result == {
        "results": [
            {
                "messageId": "message-4",
                "status": "error",
                "error": "augmentation failed",
            }
        ],
        "batchItemFailures": [{"itemIdentifier": "message-4"}],
    }


def test_handler_returns_mixed_batch_results(mocker) -> None:
    """Tests that the handler returns a mixed batch of success and error results.

    :param mocker: The pytest-mock fixture for mocking objects.
    """

    class ConditionalAugmenter:
        def __init__(self, document: str, nonstandard_codes: list[object], config: object):
            self.document = document
            self.nonstandard_codes = nonstandard_codes
            self.config = config
            self.augmented_xml = (
                '<ClinicalDocument><id root="augmented-doc-id" /></ClinicalDocument>'
            )

        def augment(self) -> Metadata:
            if self.document == "<broken />":
                raise ValueError("broken document")
            return Metadata(
                original_eicr_id="original-doc-id",
                augmented_eicr_id="augmented-doc-id",
                nonstandard_codes=[],
            )

    mocker.patch.object(lambda_function, "EICRAugmenter", ConditionalAugmenter)

    event = {
        "Records": [
            {
                "messageId": "message-5",
                "body": json.dumps(
                    {
                        "eicr_id": "source-eicr-id-1",
                        "eicr": "<ClinicalDocument />",
                        "nonstandard_codes": [],
                    }
                ),
            },
            {
                "messageId": "message-6",
                "body": json.dumps(
                    {
                        "eicr_id": "source-eicr-id-2",
                        "eicr": "<broken />",
                        "nonstandard_codes": [],
                    }
                ),
            },
        ]
    }

    result = lambda_function.handler(event, None)

    assert result == {
        "results": [
            {
                "messageId": "message-5",
                "status": "success",
                "result": {
                    "augmented_eicr": '<ClinicalDocument><id root="augmented-doc-id" /></ClinicalDocument>',
                    "metadata": {
                        "original_eicr_id": "original-doc-id",
                        "augmented_eicr_id": "augmented-doc-id",
                        "nonstandard_codes": [],
                        "error": None,
                    },
                },
            },
            {
                "messageId": "message-6",
                "status": "error",
                "error": "broken document",
            },
        ],
        "batchItemFailures": [{"itemIdentifier": "message-6"}],
    }
