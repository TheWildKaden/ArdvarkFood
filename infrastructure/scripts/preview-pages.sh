#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "$0")/../.." && pwd)"
exec python3 -m http.server 4173 --bind 0.0.0.0 --directory "$repo_root/docs"
