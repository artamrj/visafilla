#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"
mkdir -p input output

on_error() {
  printf '\nCould not start VisaFilla. See the message above.\n'
  if [ "$#" -eq 0 ] && [ -t 0 ]; then
    read -r -p 'Press Return to close… ' || true
  fi
}
launcher_arg_count=$#
trap 'status=$?; if [ "$launcher_arg_count" -eq 0 ]; then on_error; fi; exit "$status"' ERR

if ! .venv/bin/python -c 'import sys; assert sys.version_info >= (3, 12)' 2>/dev/null; then
  python_bin=''
  for candidate in python3.14 python3.13 python3.12 python3; do
    if command -v "$candidate" >/dev/null 2>&1 && "$candidate" -c 'import sys; assert sys.version_info >= (3, 12)' 2>/dev/null; then
      python_bin="$candidate"
      break
    fi
  done
  if [ -z "$python_bin" ]; then
    printf 'Python 3.12 or newer is required. Install it from python.org, then open this launcher again.\n'
    if [ "$launcher_arg_count" -eq 0 ]; then on_error; fi
    exit 1
  fi
  "$python_bin" -m venv .venv
fi

if ! .venv/bin/python - <<'PY'
import importlib.metadata as md
import re
import tomllib
from pathlib import Path

deps = tomllib.loads(Path('pyproject.toml').read_text())['project']['dependencies']
for spec in deps:
    name, expected = re.split(r'[<>=!~]+', spec, maxsplit=1)[:2]
    if md.version(name) != expected:
        raise SystemExit(f'{name} {expected} required')
import pymupdf
import pydantic
PY
then
  printf '\nSetting up the app. First-time setup needs internet access.\n'
  .venv/bin/python -m pip install -e .
fi

if [ "$#" -eq 0 ]; then
  printf '\nOpening VisaFilla. Keep this window open while using the app.\n'
  .venv/bin/python -m webapp --open
else
  .venv/bin/python -m script "$@"
fi
