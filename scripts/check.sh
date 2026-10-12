#!/usr/bin/env bash
# The single gate. Exits 0 only when every check passes.
set -euo pipefail
cd "$(dirname "$0")/.."

step() { printf '\n\033[1m== %s ==\033[0m\n' "$1"; }

step "ruff (lint)";        uv run ruff check backend tests scripts
step "ruff (format)";      uv run ruff format --check backend tests scripts
step "mypy";               uv run mypy
step "pytest";             uv run pytest -q
step "tsc";                (cd frontend && npx tsc -b --noEmit)
step "eslint";             (cd frontend && npx eslint .)
step "vitest";             (cd frontend && npx vitest run)
step "frontend build";     (cd frontend && npm run build)
step "playwright (e2e)";   (cd frontend && npx playwright test)
step "server log is clean"
# A request can fail inside the server while every UI assertion still passes; don't let it hide.
if ! grep -q "VideoDownloader listening" test-results/e2e-server.log; then
  echo "The e2e server log was not captured, so it cannot be checked." >&2
  exit 1
fi
if grep -n "Traceback\|Exception in ASGI" test-results/e2e-server.log; then
  echo "The server logged an exception during the e2e run (see above)." >&2
  exit 1
fi
echo "no exceptions in test-results/e2e-server.log"

# The native app: build and sign (app + Safari extension), then run its UI tests. The UI tests
# launch the app, so a window appears briefly.
XCODE=(xcodebuild -quiet -project macos/VideoDownloader/VideoDownloader.xcodeproj -scheme VideoDownloader
       -derivedDataPath macos/build -allowProvisioningUpdates)
step "Swift (VideoDownloaderKit)"; (cd macos/VideoDownloaderKit && swift test --quiet)
step "macOS app (build)";  "${XCODE[@]}" build
rm -rf macos/build/ui-tests.xcresult
step "macOS app (UI tests)"; "${XCODE[@]}" -resultBundlePath macos/build/ui-tests.xcresult test
step "native screenshots"; uv run python scripts/export_ui_screenshots.py macos/build/ui-tests.xcresult

printf '\n\033[32m\033[1mALL CHECKS PASSED\033[0m\n'
