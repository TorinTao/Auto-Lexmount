import json
import os
import shutil
import subprocess
import sys
import uuid
import resource
from pathlib import Path

from .common import WorkflowError, redact
from .demo import CODE


def execute(project, demo=False, timeout=45):
    project = Path(project).resolve()
    output = project / "output.json"
    if output.exists():
        output.unlink()
    if demo:
        if (project / "main.py").read_text() != CODE:
            raise WorkflowError("Local demo execution only permits the exact trusted fixture")
        command = [sys.executable, "-I", "main.py"]
    else:
        if not shutil.which("docker"):
            raise WorkflowError("Docker is required for generated code; install Docker and pull python:3.12-slim")
        name = "autolex-" + uuid.uuid4().hex[:12]
        command = ["docker", "run", "--rm", "--name", name, "--network", "none", "--read-only",
                   "--cap-drop", "ALL", "--security-opt", "no-new-privileges", "--pids-limit", "64",
                   "--memory", "256m", "--cpus", "1", "--ulimit", "fsize=2000000:2000000", "--user", f"{os.getuid()}:{os.getgid()}",
                   "--tmpfs", "/tmp:rw,noexec,nosuid,size=16m", "-v", f"{project}:/work:rw",
                   "-w", "/work", "python:3.12-slim", "python", "-I", "main.py"]
    # Bound stdout on the host too; container memory limits do not bound log size.
    log = project.parent / "execution.log"
    try:
        with log.open("w") as stream:
            proc = subprocess.run(command, cwd=project, stdout=stream, stderr=stream,
                                  timeout=timeout, env={"PATH": os.environ.get("PATH", ""), "HOME": "/tmp"},
                                  preexec_fn=lambda: resource.setrlimit(resource.RLIMIT_FSIZE, (2_000_000, 2_000_000)))
        with log.open() as stream:
            transcript = redact(stream.read(16000))
        return {"returncode": proc.returncode, "log": transcript, "timeout": False}
    except subprocess.TimeoutExpired:
        if not demo:
            subprocess.run(["docker", "rm", "-f", name], capture_output=True, timeout=15)
        return {"returncode": -1, "log": "Execution timed out", "timeout": True}


def validate_output(project, input_data):
    path = Path(project) / "output.json"
    failures = []
    if not path.is_file() or path.is_symlink() or path.stat().st_size > 1_000_000:
        return ["output.json missing, symlink, or larger than 1 MB"]
    try:
        result = json.loads(path.read_text())
        items = result["items"]
        if not isinstance(items, list) or not items:
            return ["items must be a nonempty list"]
        expected = {page["url"] for page in input_data["pages"]}
        source_text = {page["url"]: " ".join(page["result"]["main_text"].split()) for page in input_data["pages"]}
        point_ids = set()
        seen = set()
        for item in items:
            if not isinstance(item, dict):
                failures.append("Each item must be an object")
                continue
            url = item.get("url")
            if not isinstance(url, str) or url not in expected:
                failures.append("Item source URL not present in fetched evidence")
            elif url in seen:
                failures.append("Duplicate source URL")
            else:
                seen.add(url)
            for field in ("title", "summary"):
                if not isinstance(item.get(field), str) or not item[field].strip():
                    failures.append(f"Missing nonempty {field}")
            points = item.get("points", [])
            absent = item.get("not_mentioned", [])
            if not isinstance(absent, list) or any(not isinstance(topic, str) or not topic.strip() for topic in absent):
                failures.append("not_mentioned must be a list of nonempty topic strings")
            if not isinstance(points, list):
                failures.append("points must be a list")
                continue
            for point in points:
                if not isinstance(point, dict) or any(not isinstance(point.get(key), str) or not point[key].strip() for key in ("id", "summary", "quote")):
                    failures.append("Point requires nonempty id, summary and quote")
                    continue
                if point["id"] in point_ids:
                    failures.append("Duplicate point ID")
                point_ids.add(point["id"])
                if "url" in point and point["url"] != url:
                    failures.append("Point URL must match its parent page")
                quote = " ".join(point["quote"].split())
                if len(quote.split()) > 25:
                    failures.append(f"Quote exceeds 25 words: {point['id']} has {len(quote.split())}; select a shorter contiguous excerpt supporting the same claim")
                if not isinstance(url, str) or quote not in source_text.get(url, ""):
                    import difflib
                    original = source_text.get(url, "") if isinstance(url, str) else ""
                    match = difflib.SequenceMatcher(None, quote, original, autojunk=False).find_longest_match()
                    excerpt = original[max(0, match.b - 30):match.b + min(match.size, 180) + 50]
                    failures.append("Quote not present in cited page: " + point["id"] +
                                    ". Preserve exact punctuation; shorten the quote if needed. Original excerpt: " + excerpt)
        if seen != expected:
            failures.append("Every fetched page must appear in the output")
        conclusions = result.get("conclusions", [])
        if not isinstance(conclusions, list):
            failures.append("conclusions must be a list")
        else:
            for conclusion in conclusions:
                if not isinstance(conclusion, dict) or not isinstance(conclusion.get("text"), str) or not conclusion["text"].strip():
                    failures.append("Conclusion requires nonempty text")
                    continue
                refs = conclusion.get("point_refs")
                if not isinstance(refs, list) or not refs or any(not isinstance(ref, str) or ref not in point_ids for ref in refs):
                    failures.append("Conclusion must refer to existing point IDs")
    except (ValueError, KeyError, TypeError, UnicodeError):
        failures.append("Invalid output JSON schema")
    return failures
