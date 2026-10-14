#!/bin/bash
# Xcode build phase of the app target: put the backend inside the app (PLAN P8, release flavour).
#   Contents/Resources/backend/app      the server's source
#   Contents/Resources/backend-project  pyproject.toml, uv.lock, .python-version
#   Contents/Helpers/uv                 the uv that installs Python and the packages
# A Debug build still runs the checkout (VDProjectRoot); it carries these too, so the release
# flavour can be tried from it. VD_BUNDLE_UV names the uv to carry (the release script passes
# a universal one); otherwise Homebrew's is used.
set -euo pipefail

ROOT="${SRCROOT}/../.."
RESOURCES="${TARGET_BUILD_DIR}/${UNLOCALIZED_RESOURCES_FOLDER_PATH}"
HELPERS="${TARGET_BUILD_DIR}/${CONTENTS_FOLDER_PATH}/Helpers"

mkdir -p "$RESOURCES/backend" "$RESOURCES/backend-project" "$HELPERS"
rsync -a --delete --exclude "__pycache__" --exclude "*.pyc" "$ROOT/backend/app/" "$RESOURCES/backend/app/"
cp "$ROOT/pyproject.toml" "$ROOT/uv.lock" "$ROOT/.python-version" "$RESOURCES/backend-project/"

UV="${VD_BUNDLE_UV:-}"
if [ -z "$UV" ]; then
  for candidate in /opt/homebrew/bin/uv /usr/local/bin/uv "$HOME/.local/bin/uv"; do
    if [ -x "$candidate" ]; then UV="$candidate"; break; fi
  done
fi
if [ -z "$UV" ]; then
  echo "warning: no uv to carry; the release flavour of this build cannot install its runtime"
  exit 0
fi
cp -f "$UV" "$HELPERS/uv"
chmod 755 "$HELPERS/uv"
# Nested code is not signed by Xcode's own step: sign it with the app's identity first.
if [ "${CODE_SIGNING_ALLOWED:-YES}" = "YES" ] && [ -n "${EXPANDED_CODE_SIGN_IDENTITY:-}" ]; then
  codesign --force --sign "$EXPANDED_CODE_SIGN_IDENTITY" --options runtime --timestamp=none "$HELPERS/uv"
fi
