import io
import json
import unittest
import urllib.error
from unittest.mock import patch

from autolex.clients import post_json
from autolex.common import WorkflowError


class TransportTests(unittest.TestCase):
    def test_wire_request_and_utf8_response(self):
        with patch("urllib.request.urlopen", return_value=io.BytesIO('{"title":"中文"}'.encode())) as open_url:
            result = post_json("https://example.com/v1/extract", {"extract": {"url": "https://example.com"}}, {"X-API-Key": "test-key"})
        self.assertEqual(result["title"], "中文")
        request = open_url.call_args.args[0]
        self.assertEqual(request.get_method(), "POST")
        self.assertEqual(json.loads(request.data), {"extract": {"url": "https://example.com"}})
        self.assertEqual(request.get_header("X-api-key"), "test-key")

    def test_http_error_hides_server_body(self):
        error = urllib.error.HTTPError("https://example.com", 401, "sensitive details", {}, None)
        with patch("urllib.request.urlopen", side_effect=error), self.assertRaisesRegex(WorkflowError, "^API returned HTTP 401$"):
            post_json("https://example.com", {}, {})

    def test_connection_and_timeout_errors(self):
        for error in (urllib.error.URLError("secret in URL"), TimeoutError()):
            with patch("urllib.request.urlopen", side_effect=error), self.assertRaises(WorkflowError) as raised:
                post_json("https://example.com", {}, {})
            self.assertNotIn("secret", str(raised.exception))

    def test_invalid_json_and_oversized_response(self):
        for content in (b"not json", b"x" * 4_000_001):
            with patch("urllib.request.urlopen", return_value=io.BytesIO(content)), self.assertRaises(WorkflowError):
                post_json("https://example.com", {}, {})


if __name__ == "__main__":
    unittest.main()
