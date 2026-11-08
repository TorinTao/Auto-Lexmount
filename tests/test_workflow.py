import hashlib
import json
import os
import subprocess
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from autolex.clients import LexmountFetch, Model
from autolex.common import WorkflowError, public_url, read_json, redact, write_json
from autolex.demo import CODE, DemoFetch, DemoModel
from autolex.runner import execute, validate_output
from autolex.submission import submit
from autolex.workflow import Workflow, select_idea, validate_code, validate_rules


class InTemp(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)


class Validators(unittest.TestCase):
    def test_public_url(self):
        for url in ["file:///etc/passwd", "http://localhost", "http://127.0.0.1", "http://10.1.1.1", "https://u:p@example.com", "http://[::1]"]:
            with self.subTest(url=url), self.assertRaises(WorkflowError):
                public_url(url)
        self.assertEqual(public_url("https://example.com"), "https://example.com")

    def test_rule_quotes(self):
        rules = DemoModel().ask("RULES", {})
        validate_rules(rules, DemoFetch().fetch("https://example.com")["result"]["main_text"])
        with self.assertRaises(WorkflowError):
            validate_rules(rules, "No such rule")

    def test_naive_deadline_rejected(self):
        rules = DemoModel().ask("RULES", {})
        rules["deadline"] = "2026-11-08"
        with self.assertRaises(WorkflowError):
            validate_rules(rules, "Use Lexmount cloud.")

    def test_rule_punctuation_error_reports_exact_source_fragment(self):
        source = '获奖前须确认官网展示授权；发布前核对内容与署名。'
        rules = {'title': '规则', 'requirements': [{'text': '授权', 'quote': '获奖前须确认官网展示授权。'}]}
        with self.assertRaises(WorkflowError) as error:
            validate_rules(rules, source)
        self.assertIn(source, str(error.exception))
        rules['requirements'][0]['quote'] = '获奖前须确认官网展示授权'
        validate_rules(rules, source)

    def test_select_best_idea(self):
        data = DemoModel().ask("IDEAS", {})
        data["ideas"].append({**data["ideas"][0], "title": "Better", "score": 99})
        self.assertEqual(select_idea(data)["title"], "Better")

    def test_sections_of_one_document_are_not_duplicate_sources(self):
        data = DemoModel().ask('IDEAS', {})
        urls = ['https://example.com/doc', 'https://example.com/doc#section']
        data['ideas'][0]['source_urls'] = urls
        selected = select_idea(data)
        self.assertEqual(selected['source_urls'], ['https://example.com/doc'])
        self.assertEqual(selected['source_sections'], urls)

    def test_bad_score_and_empty_sources(self):
        for update in ({"score": 101}, {"score": True}, {"source_urls": []}):
            data = DemoModel().ask("IDEAS", {})
            data["ideas"][0].update(update)
            with self.assertRaises(WorkflowError):
                select_idea(data)

    def test_invalid_code(self):
        for code in ("", "def bad syntax", None):
            with self.assertRaises(WorkflowError):
                validate_code({"code": code})

    def test_secret_redaction(self):
        with patch.dict(os.environ, {"MODEL_API_KEY": "test-secret-value"}):
            self.assertNotIn("test-secret-value", redact("Oops test-secret-value"))


class ClientTests(unittest.TestCase):
    def test_http_api_request_and_evidence(self):
        response = {"request_id": "request-1", "result": {"main_text": "Evidence", "status_code": 200}}
        with patch.dict(os.environ, {"LEXMOUNT_API_KEY": "secret", "LEXMOUNT_PROJECT_ID": "project"}, clear=True), patch("autolex.clients.post_json", return_value=response) as post:
            evidence = LexmountFetch().fetch("https://example.com")
            self.assertEqual(evidence["request_id"], "request-1")
            self.assertFalse(evidence["demo"])
            self.assertEqual(post.call_args.args[1], {"extract": {"url": "https://example.com"}})
            self.assertEqual(post.call_args.args[2]["X-Project-Id"], "project")

    def test_api_empty_and_error_results(self):
        for data in ({"error": {"message": "bad"}}, {"result": {}}, {"result": {"main_text": "404", "status_code": 404}}):
            with patch.dict(os.environ, {"LEXMOUNT_API_KEY": "key", "LEXMOUNT_PROJECT_ID": "id"}, clear=True), patch("autolex.clients.post_json", return_value=data), self.assertRaises(WorkflowError):
                LexmountFetch().fetch("https://example.com")

    def test_cli_failure(self):
        with patch.dict(os.environ, {"LEXMOUNT_FETCH_CLI": "/missing-cli"}, clear=True), self.assertRaises(WorkflowError):
            LexmountFetch().fetch("https://example.com")

    def test_missing_credentials(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(WorkflowError):
                LexmountFetch().fetch("https://example.com")
            with self.assertRaises(WorkflowError):
                Model().ask("task", {})

    def test_model_output_and_budget(self):
        with patch.dict(os.environ, {"MODEL_API_KEY": "secret", "MODEL_NAME": "model"}), patch("autolex.clients.post_json", return_value={"choices": [{"message": {"content": '{"ok": true}'}}]}):
            model = Model(max_calls=1)
            self.assertTrue(model.ask("task", {})["ok"])
            with self.assertRaises(WorkflowError):
                model.ask("task", {})

    def test_model_malformed_response(self):
        with patch.dict(os.environ, {"MODEL_API_KEY": "secret", "MODEL_NAME": "model"}), patch("autolex.clients.post_json", return_value={"choices": []}), self.assertRaises(WorkflowError):
            Model().ask("task", {})


class RunnerTests(InTemp):
    def test_quotes_and_conclusions_are_grounded(self):
        data = self.prepare()
        item = {"url": "https://example.com", "title": "T", "summary": "S", "points": [
            {"id": "p1", "summary": "Use cloud", "quote": "Use Lexmount cloud.", "url": "https://example.com"}]}
        output = {"items": [item], "conclusions": [{"text": "Use cloud", "point_refs": ["p1"]}]}
        write_json(self.root / "output.json", output)
        self.assertEqual(validate_output(self.root, data), [])
        item["points"][0]["quote"] = "Invented source text"
        output["conclusions"][0]["point_refs"] = ["missing"]
        write_json(self.root / "output.json", output)
        failures = validate_output(self.root, data)
        self.assertTrue(any("Quote not present" in failure for failure in failures))
        self.assertTrue(any("existing point IDs" in failure for failure in failures))

    def prepare(self):
        (self.root / "main.py").write_text(CODE)
        data = {"pages": [DemoFetch().fetch("https://example.com")]}
        write_json(self.root / "input.json", data)
        return data

    def test_trusted_fixture_execution(self):
        data = self.prepare()
        self.assertEqual(execute(self.root, demo=True)["returncode"], 0)
        self.assertEqual(validate_output(self.root, data), [])

    def test_arbitrary_demo_code_refused(self):
        self.prepare()
        (self.root / "main.py").write_text("print('untrusted')")
        with self.assertRaises(WorkflowError):
            execute(self.root, demo=True)

    def test_stale_output_removed(self):
        self.prepare()
        write_json(self.root / "output.json", {"old": True})
        with patch("autolex.runner.subprocess.run", return_value=subprocess.CompletedProcess([], 1)):
            execute(self.root, demo=True)
        self.assertFalse((self.root / "output.json").exists())

    def test_missing_docker(self):
        self.prepare()
        with patch("autolex.runner.shutil.which", return_value=None), self.assertRaises(WorkflowError):
            execute(self.root)

    def test_container_limits_and_timeout_cleanup(self):
        self.prepare()
        with patch("autolex.runner.shutil.which", return_value="/bin/docker"), patch("autolex.runner.subprocess.run", side_effect=[subprocess.TimeoutExpired("docker", 1), subprocess.CompletedProcess([], 0)]) as run:
            result = execute(self.root, timeout=1)
            self.assertTrue(result["timeout"])
            cmd = run.call_args_list[0].args[0]
            self.assertIn("--read-only", cmd)
            self.assertIn("fsize=2000000:2000000", cmd)
            self.assertIn("none", cmd)
            self.assertEqual(run.call_args_list[1].args[0][:3], ["docker", "rm", "-f"])

    def test_output_schema_and_provenance(self):
        data = self.prepare()
        for result in ({"items": []}, {"items": [{"url": "https://forged.example", "title": "T", "summary": "S"}]}, {"items": [None]}, {"items": [{"url": [], "title": "T", "summary": "S"}]}, []):
            write_json(self.root / "output.json", result)
            self.assertTrue(validate_output(self.root, data))

    def test_duplicate_sources(self):
        data = self.prepare()
        item = {"url": "https://example.com", "title": "T", "summary": "S"}
        write_json(self.root / "output.json", {"items": [item, item]})
        self.assertIn("Duplicate source URL", validate_output(self.root, data))

    def test_symlink_output_rejected(self):
        data = self.prepare()
        (self.root / "output.json").symlink_to(self.root / "input.json")
        self.assertTrue(validate_output(self.root, data))


class WorkflowTests(InTemp):
    def test_live_acceptance_failure_prevents_packaging(self):
        class RejectingModel(DemoModel):
            def ask(self, task, context):
                if task.startswith("REVIEW"):
                    self.calls += 1
                    return {"passed": False, "checks": [{"requirement": "coverage", "passed": False, "reason": "missing"}], "issues": ["Missing required content"]}
                return super().ask(task, context)
        with self.assertRaises(WorkflowError):
            Workflow(self.root, "https://example.com", demo=False, repairs=0, fetcher=DemoFetch(), model=RejectingModel(),
                     executor=lambda project, **kwargs: execute(project, demo=True)).run()
        self.assertFalse((self.root / "submission.zip").exists())
        self.assertIn("Missing required content", read_json(self.root / "tests.json")["attempts"][0]["failures"])

    def workflow(self, **kwargs):
        return Workflow(self.root, "https://example.com", demo=True, **kwargs)

    def test_full_workflow_and_archive(self):
        state = self.workflow().run()
        self.assertEqual(state["status"], "ready")
        self.assertEqual(state["completed"], ["rules", "ideas", "build", "test", "package"])
        with zipfile.ZipFile(self.root / "submission.zip") as archive:
            self.assertIn("manifest.json", archive.namelist())
            self.assertIn("DEMO", archive.read("submission.md").decode())
            for name, digest in json.loads(archive.read("manifest.json")).items():
                self.assertEqual(hashlib.sha256(archive.read(name)).hexdigest(), digest)

    def test_resume_does_not_repeat_calls(self):
        model = DemoModel()
        self.workflow(model=model).run("ideas")
        self.assertEqual(model.calls, 2)
        second = DemoModel()
        self.workflow(model=second).run()
        self.assertEqual(second.calls, 3)
        self.workflow().run()

    def test_saved_artifact_tampering(self):
        self.workflow().run("rules")
        (self.root / "rules.json").write_text("{}")
        with self.assertRaises(WorkflowError):
            self.workflow().run()

    def test_mode_change_rejected(self):
        self.workflow().run("rules")
        with self.assertRaises(WorkflowError):
            Workflow(self.root, "https://example.com", demo=False).run()

    def test_failure_then_repair(self):
        calls = []
        def flaky(project, demo):
            calls.append(project)
            if len(calls) == 1:
                return {"returncode": 1, "log": "simulated failure", "timeout": False}
            return execute(project, demo=True)
        self.workflow(executor=flaky).run()
        report = read_json(self.root / "tests.json")
        self.assertTrue(report["passed"])
        self.assertEqual(len(report["attempts"]), 2)

    def test_repair_exhaustion_and_resume(self):
        bad = lambda *a, **k: {"returncode": 1, "log": "failure", "timeout": False}
        with self.assertRaises(WorkflowError):
            self.workflow(executor=bad, repairs=1).run()
        state = read_json(self.root / "state.json")
        self.assertEqual(state["status"], "blocked")
        self.assertNotIn("test", state["completed"])
        self.assertFalse((self.root / "submission.zip").exists())
        self.assertEqual(self.workflow().run()["status"], "ready")

    def test_fetch_failure_persisted(self):
        fetch = DemoFetch()
        fetch.fetch = lambda url: (_ for _ in ()).throw(WorkflowError("simulated outage"))
        with self.assertRaises(WorkflowError):
            self.workflow(fetcher=fetch).run()
        self.assertEqual(read_json(self.root / "state.json")["error"], "simulated outage")

    def test_concurrent_run_rejected(self):
        import fcntl
        with (self.root / ".lock").open("w") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            with self.assertRaises(WorkflowError):
                self.workflow().run()


class FakeBrowser:
    clicks = 0
    fail = False
    def __init__(self, config): pass
    def __enter__(self): return self
    def __exit__(self, *args): pass
    def fill(self, values): self.values = values
    def capture(self, path): Path(path).write_bytes(b"TEST SCREENSHOT")
    def submit(self):
        type(self).clicks += 1
        if self.fail:
            raise TimeoutError()
        return {"text": "TEST RECEIPT", "url": "https://example.com/receipt"}


class SubmissionTests(InTemp):
    def setUp(self):
        super().setUp()
        Workflow(self.root, "https://example.com", demo=True).run()
        FakeBrowser.clicks = 0
        FakeBrowser.fail = False

    def test_demo_rejected(self):
        with self.assertRaises(WorkflowError):
            submit(self.root, {}, send=True, backend=FakeBrowser)
        self.assertEqual(FakeBrowser.clicks, 0)

    def test_preview_does_not_submit(self):
        with patch("autolex.submission.preflight"):
            result = submit(self.root, {"authors": ["Test"], "artifact_links": ["https://example.com"]}, backend=FakeBrowser)
        self.assertEqual(result["status"], "preview")
        self.assertEqual(FakeBrowser.clicks, 0)

    def test_success_and_duplicate_prevention(self):
        with patch("autolex.submission.preflight"):
            result = submit(self.root, {"authors": [], "artifact_links": []}, send=True, backend=FakeBrowser)
            self.assertEqual(result["status"], "submitted")
            with self.assertRaises(WorkflowError):
                submit(self.root, {}, send=True, backend=FakeBrowser)
        self.assertEqual(FakeBrowser.clicks, 1)

    def test_uncertain_submission_not_retried(self):
        FakeBrowser.fail = True
        with patch("autolex.submission.preflight"):
            with self.assertRaises(WorkflowError):
                submit(self.root, {"authors": [], "artifact_links": []}, send=True, backend=FakeBrowser)
            self.assertEqual(read_json(self.root / "submission-state.json")["status"], "unknown")
            with self.assertRaises(WorkflowError):
                submit(self.root, {}, send=True, backend=FakeBrowser)
        self.assertEqual(FakeBrowser.clicks, 1)


if __name__ == "__main__":
    unittest.main()
