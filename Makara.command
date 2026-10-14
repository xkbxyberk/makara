#!/usr/bin/env bash
# Double-clickable launcher: builds the native app if needed, then opens it. The app starts the
# backend itself. Finder gives a bare PATH, so Homebrew is added back for the build tools.
set -euo pipefail
cd "$(dirname "$0")"
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"
APP="macos/build/Build/Products/Debug/Makara.app"
BIN="$APP/Contents/MacOS/Makara"
# The app itself: rebuild when any of its sources is newer than its executable.
if [ ! -x "$BIN" ] || [ -n "$(find macos/VideoDownloader macos/VideoDownloaderKit/Sources macos/extension -newer "$BIN" -type f -print -quit)" ]; then
  echo "Building Makara.app…"
  xcodebuild -quiet -project macos/VideoDownloader/VideoDownloader.xcodeproj -scheme VideoDownloader \
    -derivedDataPath macos/build -allowProvisioningUpdates build
fi
open "$APP"
