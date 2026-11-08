import json
import os
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse


class WorkflowError(Exception):
    pass


def now():
    return datetime.now(timezone.utc).isoformat()


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def public_url(value):
    import ipaddress
    if not isinstance(value, str):
        raise WorkflowError("URL must be a string")
    parsed = urlparse(value)
    if parsed.scheme not in {"https", "http"} or not parsed.hostname or parsed.username or parsed.password:
        raise WorkflowError("Expected an absolute public HTTP(S) URL")
    host = parsed.hostname.lower()
    if host == "localhost" or host.endswith((".localhost", ".local", ".internal")):
        raise WorkflowError("Local URLs are not supported")
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        if not address.is_global:
            raise WorkflowError("Private IP URLs are not supported")
    return value


def redact(text):
    for key, value in os.environ.items():
        if any(tag in key for tag in ("API_KEY", "TOKEN", "SECRET", "PASSWORD")) and len(value) >= 6:
            text = text.replace(value, "[REDACTED]")
    return text
