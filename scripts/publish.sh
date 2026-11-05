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

# What this app's setup assistant will download must be online, byte for byte, before anyone
# can get the app: without it no new install gets past "Kur".
MANIFEST="$ROOT/macos/VideoDownloaderKit/Sources/VideoDownloaderKit/Resources/runtime-manifest.json"
BASE=$(plutil -extract base raw -o - "$MANIFEST")
for arch in arm64 x86_64; do
  file=$(plutil -extract "archives.$arch.file" raw -o - "$MANIFEST")
  want=$(plutil -extract "archives.$arch.sha256" raw -o - "$MANIFEST")
  got=$(curl -sSfL "$BASE$file" | shasum -a 256 | awk '{print $1}')
  [ "$got" = "$want" ] || { echo "$BASE$file is not the manifest's file" >&2; exit 1; }
done

NOTES="${1:-}"
if [ -z "$NOTES" ]; then
  NOTES="$OUT/notes.md"
  printf "Makara %s for macOS 14 or later (Apple silicon and Intel).\n\nDownload **Makara-%s.dmg**, open it and drag Makara to Applications. Installed copies update themselves.\n" \
    "$VERSION" "$VERSION" > "$NOTES"
fi
gh release create "v$VERSION" --repo xkbxyberk/makara-releases --title "Makara $VERSION" \
  --notes-file "$NOTES" --latest "$DMG" "$DMG.sha256" "$OUT/appcast.xml"

# The feed installed copies read, as they read it. GitHub took 25 s to serve a new one. Captured,
# not piped into grep -q: pipefail would fail on SIGPIPE.
for _ in {1..24}; do
  feed=$(curl -sSfL https://github.com/xkbxyberk/makara-releases/releases/latest/download/appcast.xml 2>/dev/null || true)
  [[ "$feed" == *"Makara-$VERSION.dmg"* ]] && exit 0
  sleep 5
done
echo "the feed does not offer $VERSION" >&2
exit 1
