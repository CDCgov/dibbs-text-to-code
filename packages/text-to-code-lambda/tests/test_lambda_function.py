import json

import pytest
from text_to_code_lambda import lambda_function


class TestHandler:
    def test_handler(self):
        """Test handler."""
        resp = lambda_function.handler({}, {})
        assert resp == {"statusCode": 200, "message": "TTC processed successfully!"}