import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from autolex.clients import Model
from autolex.clients import LexmountFetch
from autolex.common import WorkflowError
from autolex.config import configure_deepseek, load_environment


class ConfigurationTests(unittest.TestCase):
    def test_invalid_model_json_retried_once_within_budget(self):
        blank = {"choices": [{"message": {"content": "   "}}]}
        valid = {"choices": [{"message": {"content": '{"ok":true}'}}]}
        with patch.dict(os.environ, {"MODEL_API_KEY": "test", "MODEL_NAME": "model"}, clear=True), patch("autolex.clients.post_json", side_effect=[blank, valid]):
            model = Model(max_calls=2)
            self.assertTrue(model.ask("JSON", {})["ok"])
            self.assertEqual(model.calls, 2)
        with patch.dict(os.environ, {"MODEL_API_KEY": "test", "MODEL_NAME": "model"}, clear=True), patch("autolex.clients.post_json", return_value=blank) as post:
            with self.assertRaises(WorkflowError):
                Model(max_calls=1).ask("JSON", {})
            self.assertEqual(post.call_count, 1)

    def test_cli_explicit_engine_reuses_snapshot(self):
        with patch.dict(os.environ, {"LEXMOUNT_FETCH_CLI": "/fixture", "LEXMOUNT_FETCH_ENGINE": "http"}, clear=True), patch.object(LexmountFetch, "cli_request", side_effect=[{"dom_id": "snapshot-123"}, {"main_text": "actual page", "request_id": "request-123"}]) as request:
            result = LexmountFetch().fetch("https://example.com")
        self.assertEqual(request.call_args_list[0].args[1], ["dump-dom", "--url", "https://example.com", "--engine", "http"])
        self.assertEqual(request.call_args_list[1].args[1], ["extract", "--dom-id", "snapshot-123"])
        self.assertEqual(result["request_id"], "request-123")

    def test_missing_dom_id_does_not_extract(self):
        with patch.dict(os.environ, {"LEXMOUNT_FETCH_CLI": "/fixture", "LEXMOUNT_FETCH_ENGINE": "http"}, clear=True), patch.object(LexmountFetch, "cli_request", return_value={}) as request, self.assertRaises(WorkflowError):
            LexmountFetch().fetch("https://example.com")
        self.assertEqual(request.call_count, 1)

    def test_write_private_config_and_load(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / ".env"
            with patch("getpass.getpass", return_value="sk-test-only-not-real"):
                result = configure_deepseek(path)
            self.assertNotIn("sk-test", str(result))
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            with patch.dict(os.environ, {}, clear=True):
                load_environment(path)
                self.assertEqual(os.environ["MODEL_NAME"], "deepseek-flash")
                self.assertEqual(os.environ["MODEL_BASE_URL"], "https://api.deepseek.com")
            with self.assertRaises(WorkflowError):
                configure_deepseek(path)

    def test_environment_override_and_no_shell_evaluation(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "config"
            path.write_text("MODEL_NAME='deepseek-flash'\n")
            with patch.dict(os.environ, {"MODEL_NAME": "override"}, clear=True):
                load_environment(path)
                self.assertEqual(os.environ["MODEL_NAME"], "override")
            for content in ("MODEL_API_KEY=$(whoami)", "LD_PRELOAD=bad", "MODEL_NAME='unclosed"):
                path.write_text(content)
                with self.assertRaises(WorkflowError):
                    load_environment(path)

    def test_deepseek_structured_request(self):
        env = {"MODEL_API_KEY": "test", "MODEL_NAME": "deepseek-flash", "MODEL_BASE_URL": "https://api.deepseek.com",
               "MODEL_JSON_MODE": "true", "MODEL_MAX_TOKENS": "8192"}
        reply = {"choices": [{"message": {"content": '{"ok":true}'}, "finish_reason": "stop"}]}
        with patch.dict(os.environ, env, clear=True), patch("autolex.clients.post_json", return_value=reply) as post:
            self.assertTrue(Model().ask("JSON check", {})["ok"])
        self.assertEqual(post.call_args.args[0], "https://api.deepseek.com/chat/completions")
        self.assertEqual(post.call_args.args[1]["response_format"], {"type": "json_object"})
        self.assertEqual(post.call_args.args[1]["max_tokens"], 8192)

    def test_truncation_rejected(self):
        with patch.dict(os.environ, {"MODEL_API_KEY": "test", "MODEL_NAME": "model"}, clear=True), patch("autolex.clients.post_json", return_value={"choices": [{"finish_reason": "length"}]}), self.assertRaisesRegex(WorkflowError, "truncated"):
            Model().ask("JSON", {})


if __name__ == "__main__":
    unittest.main()
