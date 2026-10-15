#!/bin/bash
# Makara's public release (PLAN P8): a universal, Developer ID-signed, notarized Makara.dmg.
#
#   scripts/release.sh 1.0 [build]        version shown to users, build number (default: the
#                                         date and time, so every release counts higher)
#   NOTARIZE=0 scripts/release.sh 1.0     everything but Apple's notary service (a trial)
#
# Needs: Xcode signed in to team V88QY49A4T with a "Developer ID Application" certificate, and
# (to notarize) a keychain profile made once with
#   xcrun notarytool store-credentials makara --apple-id <Apple ID> --team-id V88QY49A4T
# and the Sparkle key made once with build/sparkle/bin/generate_keys --account makara.
# Writes build/release/Makara-<version>.dmg, its SHA-256 and appcast.xml (Sparkle's feed, signed
# with that key). Publishing is scripts/publish.sh.
set -euo pipefail

VERSION="${1:?usage: scripts/release.sh <version> [build]}"
BUILD="${2:-$(date +%Y%m%d%H%M)}"
NOTARIZE="${NOTARIZE:-1}"
TEAM=V88QY49A4T
IDENTITY="Developer ID Application: Berk Akbay ($TEAM)"
PROFILE=makara
UV_VERSION=0.12.23
UV_SHA_arm64=50487ae565ccd96e499056b4674d438f4c53170202617b4c759defe0c6a1b544
UV_SHA_x86_64=960da44cb4b73685206ddd250b19e0a117fa41095710c1038f081f5cb613efb4
SPARKLE_VERSION=2.10.0  # the package version in the Xcode project too
SPARKLE_SHA=c2bf58aa8387266ac179357b1415d6f2635f044da8be41042af32425dae6da0c
RELEASES=https://github.com/xkbxyberk/makara-releases/releases

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="$ROOT/build/release"
WORK="$OUT/work"
rm -rf "$WORK" && mkdir -p "$WORK"
cd "$WORK"

step() { printf "\n==> %s\n" "$*"; }

step "uv $UV_VERSION for both processors"
for arch in arm64 x86_64; do
  target=$([ $arch = arm64 ] && echo aarch64-apple-darwin || echo x86_64-apple-darwin)
  sha_var="UV_SHA_$arch"
  curl -sSfL -o "uv-$arch.tar.gz" "https://github.com/astral-sh/uv/releases/download/$UV_VERSION/uv-$target.tar.gz"
  echo "${!sha_var}  uv-$arch.tar.gz" | shasum -a 256 -c --quiet -
  mkdir -p "uv-$arch" && tar -xzf "uv-$arch.tar.gz" -C "uv-$arch" --strip-components 1
done
lipo -create uv-arm64/uv uv-x86_64/uv -output uv
chmod 755 uv

step "Archive (Release, universal)"
xcodebuild -quiet -project "$ROOT/macos/VideoDownloader/VideoDownloader.xcodeproj" -scheme VideoDownloader \
  -configuration Release -archivePath "$WORK/Makara.xcarchive" -allowProvisioningUpdates \
  MARKETING_VERSION="$VERSION" CURRENT_PROJECT_VERSION="$BUILD" VD_BUNDLE_UV="$WORK/uv" archive

step "Export with Developer ID"
cat > export.plist <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>method</key><string>developer-id</string>
  <key>teamID</key><string>$TEAM</string>
  <key>signingStyle</key><string>automatic</string>
</dict></plist>
PLIST
xcodebuild -quiet -exportArchive -archivePath "$WORK/Makara.xcarchive" -exportPath "$WORK/export" \
  -exportOptionsPlist export.plist -allowProvisioningUpdates
APP="$WORK/export/Makara.app"

step "Sign the carried uv with Developer ID, then the app again (inside out)"
codesign --force --sign "$IDENTITY" --options runtime --timestamp "$APP/Contents/Helpers/uv"
codesign --force --sign "$IDENTITY" --options runtime --timestamp \
  --preserve-metadata=entitlements,requirements,flags "$APP"

step "Check"
codesign --verify --deep --strict --verbose=1 "$APP"
for binary in "$APP/Contents/MacOS/Makara" "$APP/Contents/Helpers/uv" \
              "$APP/Contents/PlugIns/VideoDownloader Extension.appex/Contents/MacOS/VideoDownloader Extension"; do
  archs=$(lipo -archs "$binary")
  [[ "$archs" == *x86_64* && "$archs" == *arm64* ]] || { echo "not universal: $binary ($archs)" >&2; exit 1; }
  signature=$(codesign -dv --verbose=2 "$binary" 2>&1)  # not piped into grep -q: pipefail
  [[ "$signature" == *"Authority=$IDENTITY"* ]] || { echo "not Developer ID: $binary" >&2; exit 1; }
done
[ "$(/usr/libexec/PlistBuddy -c 'Print VDProjectRoot' "$APP/Contents/Info.plist")" = "" ] \
  || { echo "a release must not name a checkout" >&2; exit 1; }

notarize() {  # file
  xcrun notarytool submit "$1" --keychain-profile "$PROFILE" --wait --timeout 30m
}

if [ "$NOTARIZE" = 1 ]; then
  step "Notarize the app"
  ditto -c -k --keepParent "$APP" Makara-app.zip
  notarize Makara-app.zip
  xcrun stapler staple "$APP"  # so it opens offline once copied out of the disk image
fi

step "Disk image"
DMG="$OUT/Makara-$VERSION.dmg"
rm -rf dmg "$DMG" && mkdir dmg
cp -R "$APP" dmg/
ln -s /Applications dmg/Applications
hdiutil create -quiet -volname "Makara" -srcfolder dmg -fs HFS+ -format ULMO "$DMG"
codesign --sign "$IDENTITY" --timestamp "$DMG"

if [ "$NOTARIZE" = 1 ]; then
  step "Notarize the disk image"
  notarize "$DMG"
  xcrun stapler staple "$DMG"
  spctl --assess --type open --context context:primary-signature -v "$DMG"
  spctl --assess --type execute -v "$APP"
else
  echo "(not notarized: Gatekeeper will refuse this one on another Mac)"
fi

step "Sparkle feed"
curl -sSfL -o sparkle.tar.xz "https://github.com/sparkle-project/Sparkle/releases/download/$SPARKLE_VERSION/Sparkle-$SPARKLE_VERSION.tar.xz"
echo "$SPARKLE_SHA  sparkle.tar.xz" | shasum -a 256 -c --quiet -
mkdir -p sparkle && tar -xf sparkle.tar.xz -C sparkle
signature=$(sparkle/bin/sign_update --account makara "$DMG")  # sparkle:edSignature="…" length="…"
cat > "$OUT/appcast.xml" <<XML
<?xml version="1.0" encoding="utf-8"?>
<rss version="2.0" xmlns:sparkle="http://www.andymatuschak.org/xml-namespaces/sparkle">
  <channel>
    <title>Makara</title>
    <item>
      <title>Makara $VERSION</title>
      <pubDate>$(LC_ALL=C date -u "+%a, %d %b %Y %H:%M:%S +0000")</pubDate>
      <sparkle:version>$BUILD</sparkle:version>
      <sparkle:shortVersionString>$VERSION</sparkle:shortVersionString>
      <sparkle:minimumSystemVersion>14.0</sparkle:minimumSystemVersion>
      <sparkle:releaseNotesLink>$RELEASES/tag/v$VERSION</sparkle:releaseNotesLink>
      <enclosure url="$RELEASES/download/v$VERSION/Makara-$VERSION.dmg" $signature type="application/octet-stream"/>
    </item>
  </channel>
</rss>
XML
echo "$VERSION" > "$OUT/version"

shasum -a 256 "$DMG" | tee "$DMG.sha256"
du -h "$DMG"
