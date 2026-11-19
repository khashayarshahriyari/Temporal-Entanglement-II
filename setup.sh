#!/usr/bin/env bash
# One-time setup: private Python environment + libraries (+ a headless browser for JavaScript-driven calendars).
set -e
cd "$(dirname "$0")"
PY="${PYTHON:-python3}"
"$PY" -m venv .venv
. .venv/bin/activate
pip install --upgrade pip >/dev/null
pip install -r requirements.txt
echo
echo "Installing the headless browser used for JavaScript-driven calendars (about 150 MB)..."
python -m playwright install chromium || echo "(browser install failed - most venues don't need it; re-run setup.sh later to retry)"
echo
echo "Done. Next:  bash run.sh"
