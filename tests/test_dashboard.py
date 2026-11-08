import io
import json
import os
import tempfile
import threading
import time
import unittest
from email.message import Message
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from autolex.common import WorkflowError, read_json, write_json
from autolex.server import Dashboard, handler_for


class DashboardTests(unittest.TestCase):
    def test_asset_directories_are_not_runs(self):
        (self.root / "qa").mkdir()
        (self.root / "qa" / "screenshot.png").write_bytes(b"fixture")
        self.assertEqual(self.app.listing(), [])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.app = Dashboard(self.root)

    def wait(self, run_id):
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            with self.app.lock:
                active = run_id in self.app.active
            if not active:
                return self.app.detail(run_id)
            time.sleep(.01)
        self.fail("Background workflow did not finish")

    def test_create_demo_view_results_and_download(self):
        for _ in range(3):
            result = self.app.launch({"url": "https://example.com", "mode": "demo"})
            detail = self.wait(result["id"])
            self.assertEqual(detail["state"]["status"], "ready")
            self.assertTrue(detail["tests"]["passed"])
            self.assertIn("main.py", detail["artifacts"])
            self.assertIn("DEMO", detail["report"])
            self.assertTrue(self.app.artifact(result["id"], "submission.zip").is_file())
        self.assertEqual(len(self.app.listing()), 3)

    def test_pause_and_resume_from_dashboard(self):
        run_id = self.app.launch({"url": "https://example.com", "until": "ideas"})["id"]
        self.assertEqual(self.wait(run_id)["state"]["completed"], ["rules", "ideas"])
        self.app.launch({}, run_id)
        self.assertEqual(self.wait(run_id)["state"]["status"], "ready")
        with self.assertRaises(WorkflowError):
            self.app.launch({}, run_id)

    def test_live_config_required(self):
        with patch("autolex.server.configuration", return_value={"lexmount": True, "model": False, "docker": False}), self.assertRaises(WorkflowError):
            self.app.launch({"url": "https://example.com", "mode": "live"})
        self.assertEqual(self.app.listing(), [])

    def test_validation_and_traversal(self):
        for run_id in ("../outside", "a/b", ".", "a%2fb", "a b"):
            with self.assertRaises(WorkflowError):
                self.app.directory(run_id)
        for payload in ([], {"url": "file:///etc/passwd"}, {"url": "https://example.com", "mode": "oops"},
                        {"url": "https://example.com", "repairs": True}, {"url": "https://example.com", "until": "submit"}):
            with self.assertRaises(WorkflowError):
                self.app.launch(payload)

    def test_symlinks_and_private_files_refused(self):
        run_id = self.app.launch({"url": "https://example.com"})["id"]
        self.wait(run_id)
        with self.assertRaises(WorkflowError):
            self.app.artifact(run_id, ".env")
        directory = self.app.directory(run_id)
        (directory / "output.json").unlink()
        (directory / "output.json").symlink_to(directory / "state.json")
        with self.assertRaises(WorkflowError):
            self.app.artifact(run_id, "output.json")
        (directory / "state.json").unlink()
        (directory / "state.json").symlink_to(directory / "rules.json")
        with self.assertRaises(WorkflowError):
            self.app.detail(run_id)

    def test_single_worker_and_error_visibility(self):
        gate = threading.Event()
        class BlockedWorkflow:
            def __init__(self, *args, **kwargs): pass
            def run(self, *args):
                gate.wait(3)
                raise WorkflowError("Fixture failure")
        self.app.workflow = BlockedWorkflow
        run_id = self.app.launch({"url": "https://example.com"})["id"]
        try:
            with self.assertRaises(WorkflowError):
                self.app.launch({"url": "https://example.com"})
            self.assertTrue(self.app.detail(run_id)["state"]["active"])
        finally:
            gate.set()
        self.assertEqual(self.wait(run_id)["state"]["error"], "Fixture failure")

    def test_interrupted_and_external_process_detection(self):
        import fcntl
        directory = self.app.directory("interrupted")
        directory.mkdir()
        write_json(directory / "state.json", {"status": "running", "url": "https://example.com", "demo": True})
        self.assertEqual(self.app.detail("interrupted")["state"]["status"], "interrupted")
        with (directory / ".lock").open("w") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self.assertTrue(self.app.detail("interrupted")["state"]["active"])

    def request(self, method, path, body=None, token=None, host="127.0.0.1:8765", origin=None):
        # Exercise the actual HTTP handler through memory streams; no listening socket needed.
        handler = object.__new__(handler_for(self.app))
        handler.path = path
        handler.server = SimpleNamespace(server_port=8765)
        handler.headers = Message()
        handler.headers["Host"] = host
        if token is not None:
            handler.headers["X-Autolex-Token"] = token
        if origin:
            handler.headers["Origin"] = origin
        payload = json.dumps(body).encode() if body is not None else b""
        handler.headers["Content-Length"] = str(len(payload))
        handler.headers["Content-Type"] = "application/json"
        handler.rfile = io.BytesIO(payload)
        handler.wfile = io.BytesIO()
        result = {"headers": {}}
        handler.send_response = lambda code: result.update(status=code)
        handler.send_header = lambda name, value: result["headers"].update({name: value})
        handler.end_headers = lambda: None
        getattr(handler, "do_" + method)()
        result["body"] = handler.wfile.getvalue()
        return result

    def test_http_handler_health_static_and_missing(self):
        result = self.request("GET", "/api/health")
        self.assertEqual(result["status"], 200)
        self.assertEqual(json.loads(result["body"])["token"], self.app.token)
        page = self.request("GET", "/")
        self.assertIn(b"task-dialog", page["body"])
        self.assertIn("frame-ancestors 'none'", page["headers"]["Content-Security-Policy"])
        self.assertEqual(self.request("GET", "/../../.env")["status"], 404)

    def test_http_handler_origin_host_and_csrf(self):
        for options in ({"host": "evil.example:8765"}, {"origin": "https://evil.example"}):
            self.assertEqual(self.request("GET", "/api/health", **options)["status"], 403)
        self.assertEqual(self.request("POST", "/api/runs", {"url": "https://example.com"})["status"], 403)
        self.assertEqual(self.request("POST", "/api/runs", {}, token="wrong")["status"], 403)

    def test_public_proxy_origin_and_csrf(self):
        with patch.dict(os.environ, {"AUTOLEX_PUBLIC_ORIGIN": "https://39.106.14.223"}):
            self.app = Dashboard(self.root)
        host = "39.106.14.223"
        self.assertEqual(self.request("GET", "/api/health", host=host)["status"], 200)
        for origin in ("http://39.106.14.223", "https://evil.example", "null"):
            self.assertEqual(self.request("GET", "/api/health", host=host, origin=origin)["status"], 403)
        self.assertEqual(self.request("GET", "/api/health", host="other.example")["status"], 403)
        options = {"host": host, "origin": "https://39.106.14.223"}
        self.assertEqual(self.request("POST", "/api/runs", {}, **options)["status"], 403)
        self.assertEqual(self.request("POST", "/api/runs", {}, token="wrong", **options)["status"], 403)
        result = self.request("POST", "/api/runs", {"mode": "demo", "url": "https://example.com"},
                              token=self.app.token, **options)
        self.assertEqual(result["status"], 202)
        self.assertEqual(self.wait(json.loads(result["body"])["id"])["state"]["status"], "ready")
        self.assertEqual(self.request("GET", "/api/health")["status"], 200)

    def test_public_origin_must_be_explicit_https_origin(self):
        for origin in ("http://example.com", "https://example.com/", "https://user:pass@example.com",
                       "https://example.com?x=y", "https://example.com#fragment", "https://"):
            with self.subTest(origin=origin), patch.dict(os.environ, {"AUTOLEX_PUBLIC_ORIGIN": origin}):
                with self.assertRaises(WorkflowError):
                    Dashboard(self.root)

    def test_revision_creates_new_run_and_retains_parent(self):
        parent=self.app.launch({'url':'https://example.com','mode':'demo'})['id']
        original=self.wait(parent)
        before=(self.root/parent/'submission.zip').read_bytes()
        child=self.app.launch({'url':'https://example.com','mode':'demo','revision_of':parent,'feedback':'Make the explanation clearer'})['id']
        detail=self.wait(child)
        self.assertEqual(detail['state']['status'],'ready')
        self.assertEqual(detail['summary']['parent'],parent)
        self.assertEqual(detail['spec']['selected'],original['spec']['selected'])
        self.assertEqual((self.root/parent/'submission.zip').read_bytes(),before)
        self.assertNotEqual(parent,child)
        with self.assertRaises(WorkflowError):
            self.app.launch({'url':'https://example.com','mode':'demo','revision_of':parent,'feedback':''})

    def test_preview_is_readable_but_scripts_are_sandboxed(self):
        run_id=self.app.launch({'url':'https://example.com','mode':'demo'})['id']
        self.wait(run_id)
        response=self.request('GET',f'/api/runs/{run_id}/preview')
        self.assertEqual(response['status'],200)
        self.assertIn('text/html',response['headers']['Content-Type'])
        policy=response['headers']['Content-Security-Policy']
        self.assertIn('sandbox',policy)
        self.assertNotIn('allow-scripts',policy)
        self.assertNotIn('allow-same-origin',policy)
        self.assertNotIn('Content-Disposition',response['headers'])

    def test_summary_includes_history_and_title(self):
        run_id=self.app.launch({'url':'https://example.com','mode':'demo'})['id']
        self.wait(run_id)
        write_json(self.root/run_id/'test-history.json',[{'attempts':[{},{}]}])
        summary=self.app.detail(run_id)['summary']
        self.assertEqual(summary['attempts'],3)
        self.assertEqual(summary['sources'],1)
        self.assertEqual(self.app.listing()[0]['summary']['title'],summary['title'])

    def test_http_handler_complete_workflow(self):
        response = self.request("POST", "/api/runs", {"url": "https://example.com"}, token=self.app.token)
        self.assertEqual(response["status"], 202)
        run_id = json.loads(response["body"])["id"]
        self.wait(run_id)
        detail = self.request("GET", "/api/runs/" + run_id)
        self.assertEqual(json.loads(detail["body"])["state"]["status"], "ready")
        download = self.request("GET", f"/api/runs/{run_id}/files/submission.zip")
        self.assertEqual(download["status"], 200)
        self.assertTrue(download["body"].startswith(b"PK"))
        self.assertIn("attachment", download["headers"]["Content-Disposition"])


if __name__ == "__main__":
    unittest.main()
