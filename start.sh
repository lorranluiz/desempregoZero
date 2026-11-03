#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

if lsof -ti :8050 >/dev/null 2>&1; then
  echo "Servidor já está rodando em http://localhost:8050"
  exit 0
fi

source .venv/bin/activate
exec python app.py
