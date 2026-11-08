"""Protocol and CLI integration; servers are local fixtures, not cloud evidence."""
import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

from autolex.clients import LexmountFetch, Model, post_json
from autolex.common import WorkflowError, read_json, write_json
from autolex.demo import CODE, DemoFetch, DemoModel
from autolex.submission import preflight
from autolex.workflow import Workflow


class HTTPIntegration(unittest.TestCase):
    def setUp(self):
        self.requests = []
        requests = self.requests
        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                requests.append((self.path, body, dict(self.headers)))
                if self.path == "/v1/extract":
                    result = {"request_id": "LOCAL-TEST", "result": {"main_text": "Test text", "status_code": 200}}
                elif self.path == "/v1/chat/completions":
                    result = {"choices": [{"message": {"content": '{"answer": 42}'}}]}
                else:
                    self.send_response(503)
                    self.end_headers()
                    return
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps(result).encode())
            def log_message(self, *args): pass
        try:
            self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        except PermissionError:
            self.skipTest("Environment denies local socket creation; run outside restricted sandbox")
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()

    def test_fetch_and_model_over_http(self):
        with patch.dict(os.environ, {"LEXMOUNT_API_KEY": "test", "LEXMOUNT_PROJECT_ID": "test-project", "LEXMOUNT_BASE_URL": self.base,
                                    "MODEL_API_KEY": "test", "MODEL_NAME": "fixture-model", "MODEL_BASE_URL": self.base + "/v1"}, clear=True):
            evidence = LexmountFetch().fetch("https://example.com")
            answer = Model().ask("Question", evidence)
        self.assertEqual(answer["answer"], 42)
        self.assertEqual(self.requests[0][1], {"extract": {"url": "https://example.com"}})
        headers = {key.lower(): value for key, value in self.requests[0][2].items()}
        self.assertEqual(headers["x-project-id"], "test-project")
        self.assertEqual(self.requests[1][1]["model"], "fixture-model")

    def test_http_error_sanitized(self):
        with patch.dict(os.environ, {}, clear=True), self.assertRaisesRegex(WorkflowError, "HTTP 503"):
            post_json(self.base + "/failure", {}, {})


class CLIIntegration(unittest.TestCase):
    def test_demo_three_fresh_runs_and_resume(self):
        with tempfile.TemporaryDirectory() as tmp:
            for index in range(3):
                root = Path(tmp) / str(index)
                args = [sys.executable, "-m", "autolex", "demo", "--out", str(root)]
                first = subprocess.run(args, capture_output=True, text=True, timeout=15)
                self.assertEqual(first.returncode, 0, first.stderr + first.stdout)
                self.assertEqual(json.loads(first.stdout)["status"], "ready")
                second = subprocess.run(args, capture_output=True, text=True, timeout=15)
                self.assertEqual(second.returncode, 0, second.stdout)
                self.assertEqual(read_json(root / "tests.json")["passed"], True)
                self.assertEqual(read_json(root / "state.json")["model_calls"], 3)

    def test_missing_live_configuration_exits_nonzero(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = {"PATH": os.environ["PATH"]}
            proc = subprocess.run([sys.executable, "-m", "autolex", "run", "--out", tmp],
                                  env=env, capture_output=True, text=True, timeout=15)
            self.assertEqual(proc.returncode, 1)
            self.assertIn("LEXMOUNT", json.loads(proc.stdout)["error"])
            self.assertEqual(read_json(Path(tmp) / "state.json")["status"], "blocked")


class SubmissionPreflightIntegration(unittest.TestCase):
    def test_deadline_identity_evidence_and_integrity(self):
        # Synthetic transport and executor make a live-shaped run for preflight testing only.
        class TestFetch(DemoFetch):
            def fetch(self, url):
                result = super().fetch(url)
                result.update(provider="lexmount", demo=False)
                return result
        def executor(project, **kwargs):
            data = read_json(project / "input.json")
            if len(data["pages"]) != 1 or any(not p["result"]["main_text"].strip() or p["result"]["main_text"].startswith("NO_RELEVANT_SOURCE_EVIDENCE") for p in data["pages"]):
                return {"returncode": 1, "timeout": False, "log": "Missing evidence"}
            write_json(project / "output.json", {"items": [{"url": p["url"], "title": "Fixture", "summary": "Fixture"} for p in data["pages"]]})
            return {"returncode": 0, "timeout": False, "log": "test fixture"}
        config = {"url": "https://example.com/submit", "authors": ["TEST"], "artifact_links": ["https://example.com/artifact"],
                  "fields": {"title": "#title"}, "submit_selector": "#submit", "success_selector": "#receipt"}
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            Workflow(root, "https://example.com", fetcher=TestFetch(), model=DemoModel(), executor=executor).run()
            preflight(root, config)
            with self.assertRaises(WorkflowError):
                preflight(root, {**config, "authors": []})
            with patch("autolex.submission.datetime") as clock:
                from datetime import datetime, timezone
                clock.fromisoformat = datetime.fromisoformat
                clock.now.return_value = datetime(2100, 1, 1, tzinfo=timezone.utc)
                with self.assertRaisesRegex(WorkflowError, "passed"):
                    preflight(root, config)
            (root / "output.json").write_text("{}")
            with self.assertRaisesRegex(WorkflowError, "changed"):
                preflight(root, config)


if __name__ == "__main__":
    unittest.main()
