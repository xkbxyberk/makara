#!/bin/bash
# Publishes what scripts/release.sh made as release v<version> of xkbxyberk/makara-releases,
# marked latest, so its appcast.xml becomes the feed every installed Makara checks.
#   scripts/publish.sh [notes.md]      the notes default to a one-line summary
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="$ROOT/build/release"
VERSION=$(cat "$OUT/version")
DMG="$OUT/Makara-$VERSION.dmg"
[ -f "$DMG" ] && [ -f "$OUT/appcast.xml" ] || { echo "run scripts/release.sh first" >&2; exit 1; }
spctl --assess --type open --context context:primary-signature "$DMG"  # notarized, or stop here
grep -q "Makara-$VERSION.dmg" "$OUT/appcast.xml"

NOTES="${1:-}"
if [ -z "$NOTES" ]; then
  NOTES="$OUT/notes.md"
  printf "Makara %s for macOS 14 or later (Apple silicon and Intel).\n\nDownload **Makara-%s.dmg**, open it and drag Makara to Applications. Installed copies update themselves.\n" \
    "$VERSION" "$VERSION" > "$NOTES"
fi
gh release create "v$VERSION" --repo xkbxyberk/makara-releases --title "Makara $VERSION" \
  --notes-file "$NOTES" --latest "$DMG" "$DMG.sha256" "$OUT/appcast.xml"
