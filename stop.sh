#!/usr/bin/env bash
set -uo pipefail
cd "$(dirname "$0")"

PID=$(lsof -ti :8050 2>/dev/null || true)
if [ -z "$PID" ]; then
  echo "Nenhum servidor rodando na porta 8050."
  exit 0
fi

kill "$PID"
for _ in $(seq 1 20); do
  lsof -ti :8050 >/dev/null 2>&1 || break
  sleep 0.25
done
echo "Servidor parado."
