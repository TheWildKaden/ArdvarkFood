#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "$0")/.." && pwd)"
cd "$repo_root"

exec python3 -m uvicorn app:app --reload --host 0.0.0.0 --port "${PORT:-8000}"
