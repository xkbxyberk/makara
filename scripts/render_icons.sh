#!/usr/bin/env bash
# Renders every icon from its source (P5): the app icon is an Icon Composer document
# (macos/VideoDownloader/VideoDownloader/AppIcon.icon, built by Xcode itself); this script makes
# the Safari extension's PNGs from it and from the template glyphs in macos/design/.
set -euo pipefail
cd "$(dirname "$0")/.."
ICTOOL="/Applications/Xcode.app/Contents/Applications/Icon Composer.app/Contents/Executables/ictool"
ICON=macos/VideoDownloader/VideoDownloader/AppIcon.icon
IMAGES=macos/extension/images
for size in 48 96 128 256 512; do
  "$ICTOOL" "$ICON" --export-image --output-file "$IMAGES/icon-$size.png" --platform macOS \
    --rendition Default --width "$size" --height "$size" --scale 1 >/dev/null
done
for size in 16 32; do
  swift scripts/render_glyph.swift macos/design/glyph-outline.svg "$IMAGES/toolbar-$size.png" "$size"
  swift scripts/render_glyph.swift macos/design/glyph-filled.svg "$IMAGES/toolbar-active-$size.png" "$size"
done
echo "icons rendered"
