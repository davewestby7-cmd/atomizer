#!/usr/bin/env bash
# Start PsyPull on macOS / Linux:  ./run.sh   then open http://127.0.0.1:8000
set -e
cd "$(dirname "$0")"
if [ ! -d .venv ]; then
  python3 -m venv .venv
  .venv/bin/pip install -r requirements.txt
fi
[ -f config.yaml ] || cp config.example.yaml config.yaml
echo "PsyPull is starting: open http://127.0.0.1:8000"
exec .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000 "$@"
