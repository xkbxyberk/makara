#!/usr/bin/env bash
# Double-clickable launcher: builds the native app if needed, then opens it. The app starts the
# backend itself. Finder gives a bare PATH, so Homebrew is added back for the build tools.
set -euo pipefail
cd "$(dirname "$0")"
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"
APP="macos/build/Build/Products/Debug/VideoDownloader.app"
BIN="$APP/Contents/MacOS/VideoDownloader"
# The web UI the app shows is frontend/dist: rebuild it when its sources changed.
if [ ! -f frontend/dist/index.html ] || [ -n "$(find frontend/src frontend/index.html -newer frontend/dist/index.html -type f -print -quit)" ]; then
  echo "Building the web UI…"
  (cd frontend && npm run build >/dev/null)
fi
# The app itself: rebuild when any of its sources is newer than its executable.
if [ ! -x "$BIN" ] || [ -n "$(find macos/VideoDownloader macos/VideoDownloaderKit/Sources macos/extension -newer "$BIN" -type f -print -quit)" ]; then
  echo "Building VideoDownloader.app…"
  xcodebuild -quiet -project macos/VideoDownloader/VideoDownloader.xcodeproj -scheme VideoDownloader \
    -derivedDataPath macos/build -allowProvisioningUpdates build
fi
open "$APP"
