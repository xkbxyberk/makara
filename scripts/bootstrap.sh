#!/bin/bash
# A fresh Mac to a working development checkout of Makara (see DEVELOPING.md).
# Needs Xcode (App Store) and Homebrew already installed; safe to run again.
set -euo pipefail
cd "$(dirname "$0")/.."

if ! xcode-select -p 2>/dev/null | grep -q "Xcode.app"; then
  echo "Install Xcode from the App Store first, open it once, then run this again." >&2
  exit 1
fi
if ! command -v brew >/dev/null; then
  echo "Install Homebrew first (https://brew.sh), then run this again." >&2
  exit 1
fi

echo "==> Homebrew tools (Brewfile)"
brew bundle --file=Brewfile

echo "==> Python environment (uv.lock)"
uv sync

echo "==> Safari extension tests"
(cd macos/extension-tests && npm ci && npx playwright install chromium)

echo "==> Building Makara.app"
xcodebuild -quiet -project macos/VideoDownloader/VideoDownloader.xcodeproj -scheme VideoDownloader \
  -derivedDataPath macos/build -allowProvisioningUpdates build

echo
echo "Done. Start the app with: open Makara.command"
