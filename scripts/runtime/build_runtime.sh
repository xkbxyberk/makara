#!/bin/bash
# Builds the tools Makara's setup assistant installs (PLAN P8): one zip per architecture with
#   bin/ffmpeg bin/ffprobe   FFmpeg 9.0.2, static, GPL (ffmpeg.martin-riedl.de release builds)
#   bin/deno                 Deno 2.9.7 (the official release)
#   bin/aria2c               aria2 1.37.0, built here with AppleTLS and no other libraries
#   LICENSES/, SOURCES.md
# Every input is pinned by SHA-256; nothing unverified goes in. Writes the zips and
# runtime-manifest.json (paste into the app, see the end) to OUT (default: build/runtime).
# Usage: scripts/runtime/build_runtime.sh [version]   (version defaults to today, YYYY.MM.DD)
set -euo pipefail

VERSION="${1:-$(date +%Y.%m.%d)}"
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
OUT="${OUT:-$ROOT/build/runtime}"
WORK="$OUT/work"
MIN_MACOS=14.0

FFMPEG_VERSION=9.0.2
FFMPEG_BASE=https://ffmpeg.martin-riedl.de/download/macos
FFMPEG_BUILD_arm64=arm64/1789931890_9.0.2
FFMPEG_BUILD_x86_64=amd64/1789931006_9.0.2
DENO_VERSION=2.9.7
ARIA2_VERSION=1.37.0
ARIA2_SHA256=60a420ad7085eb616cb6e2bdf0a7206d68ff3d37fb5a956dc44242eb2f79b66b

mkdir -p "$WORK"
cd "$WORK"

fetch() {  # url file sha256
  local url=$1 file=$2 sha=$3
  [ -f "$file" ] || curl -sSfL -o "$file" "$url"
  echo "$sha  $file" | shasum -a 256 -c --quiet - || { echo "SHA-256 mismatch: $file" >&2; rm -f "$file"; exit 1; }
}

# Upstream publishes a .sha256 beside each FFmpeg zip and Deno zip; they are fetched over HTTPS
# and recorded in SOURCES.md. aria2's source hash is pinned above.
remote_sha() { curl -sSfL "$1" | grep -oE "[0-9a-f]{64}" | head -1; }

build_aria2() {  # arch host
  local arch=$1 host=$2 dir="$WORK/aria2-$arch"
  if [ -x "$dir/src/aria2c" ]; then return; fi
  rm -rf "$dir" && mkdir -p "$dir"
  tar -xf "$WORK/aria2-$ARIA2_VERSION.tar.xz" -C "$dir" --strip-components 1
  (cd "$dir" && MACOSX_DEPLOYMENT_TARGET=$MIN_MACOS ./configure \
      --host="$host" --build="$(uname -m | sed 's/arm64/aarch64/')-apple-darwin" \
      CC="clang -arch $arch -mmacosx-version-min=$MIN_MACOS" \
      CXX="clang++ -arch $arch -mmacosx-version-min=$MIN_MACOS" \
      --with-appletls --without-openssl --without-gnutls --without-libgcrypt --without-libnettle \
      --without-libgmp --without-libssh2 --without-sqlite3 --without-libxml2 --without-libexpat \
      --without-libcares --without-libuv --disable-nls --disable-bittorrent --disable-metalink \
      --disable-websocket > configure.log 2>&1 && make -j"$(sysctl -n hw.ncpu)" > make.log 2>&1)
  # Only the system's libraries: nothing a Mac without Homebrew lacks.
  if otool -L "$dir/src/aria2c" | tail -n +2 | grep -vqE "^\s+/(usr/lib|System/Library)/"; then
    echo "aria2c ($arch) links a non-system library" >&2; exit 1
  fi
}

fetch "https://github.com/aria2/aria2/releases/download/release-$ARIA2_VERSION/aria2-$ARIA2_VERSION.tar.xz" \
  "aria2-$ARIA2_VERSION.tar.xz" "$ARIA2_SHA256"

manifest_entries=()
for arch in arm64 x86_64; do
  echo "==> $arch"
  case $arch in
    arm64) deno_target=aarch64-apple-darwin; host=aarch64-apple-darwin; ffbuild=$FFMPEG_BUILD_arm64 ;;
    x86_64) deno_target=x86_64-apple-darwin; host=x86_64-apple-darwin; ffbuild=$FFMPEG_BUILD_x86_64 ;;
  esac
  stage="$WORK/stage-$arch"
  rm -rf "$stage" && mkdir -p "$stage/bin" "$stage/LICENSES"

  sources=""
  for tool in ffmpeg ffprobe; do
    url="$FFMPEG_BASE/$ffbuild/$tool.zip"
    sha=$(remote_sha "$url.sha256")
    fetch "$url" "$tool-$arch.zip" "$sha"
    ditto -x -k "$tool-$arch.zip" "$stage/bin"
    sources+="- $tool $FFMPEG_VERSION: $url (sha256 $sha); build script https://git.martin-riedl.de/ffmpeg/build-script\n"
  done
  url="https://github.com/denoland/deno/releases/download/v$DENO_VERSION/deno-$deno_target.zip"
  sha=$(remote_sha "$url.sha256sum")
  fetch "$url" "deno-$arch.zip" "$sha"
  ditto -x -k "deno-$arch.zip" "$stage/bin"
  sources+="- deno $DENO_VERSION: $url (sha256 $sha)\n"

  build_aria2 $arch $host
  cp "$WORK/aria2-$arch/src/aria2c" "$stage/bin/aria2c"
  strip -x "$stage/bin/aria2c"
  codesign --force --sign - "$stage/bin/aria2c"  # ad hoc: every arm64 binary must be signed
  sources+="- aria2c $ARIA2_VERSION: built from https://github.com/aria2/aria2/releases/download/release-$ARIA2_VERSION/aria2-$ARIA2_VERSION.tar.xz (sha256 $ARIA2_SHA256) by scripts/runtime/build_runtime.sh (AppleTLS, no other libraries)\n"

  for tool in ffmpeg ffprobe deno aria2c; do
    file "$stage/bin/$tool" | grep -q "$( [ $arch = arm64 ] && echo arm64 || echo x86_64)" || { echo "$tool is not $arch" >&2; exit 1; }
  done

  cp "$WORK/aria2-$arch/COPYING" "$stage/LICENSES/aria2-GPL-2.0.txt"
  curl -sSfL -o "$stage/LICENSES/ffmpeg-GPL-3.0.txt" https://www.gnu.org/licenses/gpl-3.0.txt
  curl -sSfL -o "$stage/LICENSES/deno-MIT.txt" "https://raw.githubusercontent.com/denoland/deno/v$DENO_VERSION/LICENSE.md"
  printf "# Makara runtime %s (%s)\n\nGPL source: FFmpeg https://ffmpeg.org/releases/ffmpeg-%s.tar.xz, aria2 as linked below.\n\n%b" \
    "$VERSION" "$arch" "$FFMPEG_VERSION" "$sources" > "$stage/SOURCES.md"

  zip="makara-runtime-$VERSION-$arch.zip"
  rm -f "$OUT/$zip"
  (cd "$stage" && ditto -c -k --sequesterRsrc . "$OUT/$zip")
  sha=$(shasum -a 256 "$OUT/$zip" | awk '{print $1}')
  size=$(stat -f %z "$OUT/$zip")
  manifest_entries+=("\"$arch\": {\"file\": \"$zip\", \"sha256\": \"$sha\", \"size\": $size}")
  echo "    $zip  $size bytes  $sha"
done

{
  echo "{"
  echo "  \"version\": \"$VERSION\","
  echo "  \"tools\": {\"ffmpeg\": \"$FFMPEG_VERSION\", \"deno\": \"$DENO_VERSION\", \"aria2c\": \"$ARIA2_VERSION\"},"
  echo "  \"archives\": {"
  echo "    ${manifest_entries[0]},"
  echo "    ${manifest_entries[1]}"
  echo "  }"
  echo "}"
} > "$OUT/runtime-manifest.json"
echo
echo "Wrote $OUT/runtime-manifest.json. Upload the zips as release runtime-$VERSION, then copy the"
echo "manifest to macos/VideoDownloaderKit/Sources/VideoDownloaderKit/Resources/runtime-manifest.json."
