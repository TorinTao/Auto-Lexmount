"""Explicit, inspected form mappings. A timed-out submit is never auto-retried."""
import fcntl
import hashlib
import os
from datetime import datetime, timezone
from pathlib import Path

from .common import WorkflowError, now, public_url, read_json, write_json


def preflight(root, config):
    state = read_json(root / "state.json")
    if state.get("demo") or state.get("status") != "ready" or "package" not in state.get("completed", []):
        raise WorkflowError("Only a completed live run can be submitted")
    manifest = read_json(root / "manifest.json")
    expected_manifest = state.get("hashes", {}).get("manifest.json")
    if hashlib.sha256((root / "manifest.json").read_bytes()).hexdigest() != expected_manifest:
        raise WorkflowError("Manifest changed after packaging")
    for name, digest in manifest.items():
        path = root / name
        if path.parent != root or not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            raise WorkflowError("Packaged artifact changed: " + name)
    if not read_json(root / "tests.json").get("passed"):
        raise WorkflowError("Tests did not pass")
    for page in [read_json(root / "official-page.json"), *read_json(root / "input.json")["pages"]]:
        if page.get("demo") or page.get("provider") != "lexmount":
            raise WorkflowError("Real Lexmount evidence is required")
    deadline = read_json(root / "rules.json").get("deadline")
    if not deadline or datetime.fromisoformat(deadline) <= datetime.now(timezone.utc):
        raise WorkflowError("Deadline unknown or already passed")
    if state.get("visual_enabled"):
        visual = read_json(root / "visual-review.json")
        if not visual.get("passed") or visual.get("last", {}).get("html_sha256") != hashlib.sha256((root / "index.html").read_bytes()).hexdigest():
            raise WorkflowError("Visual review missing, failed or not bound to the packaged page")
    public_url(config["url"])
    if not config.get("authors") or not config.get("artifact_links"):
        raise WorkflowError("Provide real authors and accessible artifact_links in submission config")
    for url in config["artifact_links"]:
        public_url(url)
    if not config.get("fields") or not config.get("submit_selector") or not config.get("success_selector"):
        raise WorkflowError("Inspect the actual form and configure field, submit and success selectors")
    if config["submit_selector"] == config["success_selector"]:
        raise WorkflowError("Success selector must identify a receipt, not the submit button")


class BrowserForm:
    def __init__(self, config):
        self.config = config

    def __enter__(self):
        from contextlib import ExitStack
        try:
            from lexmount import Lexmount
            from playwright.sync_api import sync_playwright
        except ImportError:
            raise WorkflowError('Install browser dependencies: pip install -e ".[browser]"') from None
        self.stack = ExitStack()
        try:
            os.environ.setdefault("LEXMOUNT_BASE_URL", "https://api.lexmount.cn")
            client = self.stack.enter_context(Lexmount())
            options = {"browser_mode": "normal"}
            if self.config.get("context_id"):
                options.update(context_id=self.config["context_id"], context_mode="read_write")
            session = self.stack.enter_context(client.sessions.create(**options))
            self.session_id = session.id
            playwright = self.stack.enter_context(sync_playwright())
            browser = playwright.chromium.connect_over_cdp(session.connect_url)
            self.stack.callback(browser.close)
            context = browser.contexts[0]
            self.page = context.pages[0] if context.pages else context.new_page()
            self.page.set_default_timeout(15000)
            self.page.goto(self.config["url"], wait_until="domcontentloaded")
            return self
        except Exception:
            self.stack.close()
            raise

    def fill(self, values):
        for name, selector in self.config["fields"].items():
            if name not in values:
                raise WorkflowError("No configured value for form field " + name)
            self.page.locator(selector).fill(values[name])

    def capture(self, path):
        self.page.screenshot(path=str(path), full_page=True)

    def submit(self):
        receipt = self.page.locator(self.config["success_selector"])
        if receipt.count() and receipt.is_visible():
            raise WorkflowError("Receipt selector already visible before submission; inspect the form mapping")
        self.page.locator(self.config["submit_selector"]).click()
        receipt.wait_for(state="visible")
        text = receipt.inner_text().strip()
        if not text:
            raise WorkflowError("Confirmation has no receipt text")
        return {"url": self.page.url, "text": text, "session_id": self.session_id}

    def __exit__(self, *args):
        return self.stack.__exit__(*args)


def submit(root, config, send=False, backend=BrowserForm):
    root = Path(root).resolve()
    with (root / ".lock").open("w") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise WorkflowError("Run is already active") from None
        receipt_path = root / "submission-state.json"
        previous = read_json(receipt_path) if receipt_path.exists() else {}
        if previous.get("status") in {"submitted", "sending", "unknown"}:
            raise WorkflowError("Submission already sent or uncertain; inspect the website before any retry")
        preflight(root, config)
        payload = read_json(root / "submission.json")
        values = {"title": payload["title"], "description": payload["description"],
                  "authors": "\n".join(config["authors"]), "artifact_links": "\n".join(config["artifact_links"]),
                  **config.get("extra_values", {})}
        with backend(config) as browser:
            browser.fill(values)
            browser.capture(root / "form-preview.png")
            if not send:
                result = {"status": "preview", "at": now()}
                write_json(receipt_path, result)
                return result
            write_json(receipt_path, {"status": "sending", "at": now()})
            try:
                receipt = browser.submit()
            except Exception:
                write_json(receipt_path, {"status": "unknown", "at": now(),
                           "reason": "Submission may have reached the server; inspect the website"})
                raise WorkflowError("Submit outcome unknown; automatic retry disabled") from None
            result = {"status": "submitted", "at": now(), "receipt": receipt}
            write_json(receipt_path, result)
            # Receipt is durable even if the screenshot fails after successful submission.
            try:
                browser.capture(root / "submission-receipt.png")
            except Exception:
                pass
            return result
