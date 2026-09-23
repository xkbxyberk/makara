#!/usr/bin/env bash
# Double-clickable launcher. Finder gives a bare PATH, so Homebrew is added back.
set -euo pipefail
cd "$(dirname "$0")"
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"
exec uv run python scripts/desktop.py
