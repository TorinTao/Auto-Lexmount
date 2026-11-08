"""Small explicit environment loader: never evaluates shell expressions."""
import os
import re
from pathlib import Path

from .common import WorkflowError

ALLOWED = {"MODEL_API_KEY", "MODEL_BASE_URL", "MODEL_NAME", "MODEL_JSON_MODE", "MODEL_MAX_TOKENS",
           "MODEL_THINKING", "MODEL_MAX_CALLS",
           "LEXMOUNT_API_KEY", "LEXMOUNT_PROJECT_ID", "LEXMOUNT_BASE_URL", "LEXMOUNT_FETCH_CLI", "LEXMOUNT_FETCH_ENGINE",
           "LEXMOUNT_BROWSER_CLI", "AUTOLEX_RELEASE_PROFILE", "AUTOLEX_VISUAL_REVIEW", "AUTOLEX_VISUAL_CDP"}


def load_environment(filename):
    path = Path(filename)
    if not path.is_file():
        raise WorkflowError("Environment file does not exist")
    parsed = {}
    for number, line in enumerate(path.read_text().splitlines(), 1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        key, sep, value = line.partition("=")
        key, value = key.strip(), value.strip()
        if not sep or key not in ALLOWED:
            raise WorkflowError(f"Unsupported configuration on line {number}")
        if value[:1] in {"'", '"'}:
            if len(value) < 2 or value[-1] != value[0]:
                raise WorkflowError(f"Unclosed quote on line {number}")
            value = value[1:-1]
        if "$" in value or "`" in value or "\x00" in value:
            raise WorkflowError(f"Shell interpolation is not supported on line {number}")
        parsed[key] = value
    for key, value in parsed.items():
        if value:
            os.environ.setdefault(key, value)


def configure_deepseek(filename=".env"):
    from getpass import getpass
    path = Path(filename)
    if path.exists() or path.is_symlink():
        raise WorkflowError("Configuration already exists; edit it locally rather than overwriting")
    key = getpass("Temporary DeepSeek key (hidden): ").strip()
    if not re.fullmatch(r"sk-[A-Za-z0-9_-]+", key):
        raise WorkflowError("Invalid API key format")
    cli = Path.home() / ".agents/skills/lexmount-webfetch/bin/webfetch-cli"
    content = (f"MODEL_API_KEY={key}\nMODEL_BASE_URL=https://api.deepseek.com\n"
               "MODEL_NAME=deepseek-flash\nMODEL_JSON_MODE=true\nMODEL_MAX_TOKENS=16384\nMODEL_THINKING=disabled\nMODEL_MAX_CALLS=20\n"
               "LEXMOUNT_BASE_URL=https://api.lexmount.cn\nLEXMOUNT_FETCH_ENGINE=http\n")
    if cli.is_file():
        content += f"LEXMOUNT_FETCH_CLI={cli}\n"
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w") as stream:
        stream.write(content)
    return {"configured": True, "provider": "DeepSeek", "model": "deepseek-flash", "credentials_printed": False}
