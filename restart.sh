#!/usr/bin/env bash
cd "$(dirname "$0")"

./stop.sh
exec ./start.sh
