#!/usr/bin/env bash
set -euo pipefail
project_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_root"
python_bin="$project_root/.venv/bin/python"
if [[ ! -x "$python_bin" ]]; then python_bin=python; fi
exec "$python_bin" -m autolex --env-file "$project_root/.env" "$@"
