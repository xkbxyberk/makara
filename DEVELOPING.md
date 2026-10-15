# Developing Makara on a new Mac

1. **Xcode** from the App Store. Open it once, accept the licence, and sign in with the Apple ID
   under Xcode > Settings > Accounts (team `V88QY49A4T`); automatic signing creates the
   development certificate again.
2. **Homebrew** from <https://brew.sh>.
3. **GitHub and the code:**
   ```bash
   brew install gh
   gh auth login                       # GitHub.com, HTTPS, log in with a web browser
   gh repo clone xkbxyberk/makara ~/VideoDownloader
   cd ~/VideoDownloader
   ```
   The folder name does not matter to the code; `~/VideoDownloader` keeps the Claude Code
   project history of the old Mac matching, if it is restored.
4. **Everything else:** `./scripts/bootstrap.sh` installs the `Brewfile` (uv, deno, ffmpeg-full,
   aria2, node, gh), runs `uv sync`, prepares the extension tests and builds the app.
5. **First start:** `open Makara.command`. Then:
   - Safari > Settings > Extensions: turn on Makara Dev and allow it on all websites (restart Safari
     after every rebuild of the extension).
   - System Settings > Privacy & Security > Full Disk Access: Makara Dev, if downloads should use the
     Safari session (CLAUDE.md gotcha 36).
   - Sign in to YouTube, Reddit, Instagram and X in Safari again.
6. **Check it:** `./scripts/check.sh` (the full gate; it opens the app window for UI tests).

A development build is "Makara Dev" (its own bundle id, port 8777, `makara-dev://` links and
`~/Movies/Makara Dev`, `~/Library/Application Support/Makara Dev`), so it runs beside an
installed Makara without touching its library. Not in git, restore from a backup if wanted:
Claude's notes for this project (`~/.claude/projects/-Users-akbay-VideoDownloader/`).

## Releasing from a new Mac

A release needs three secrets that are not in git. Back them up before formatting and keep them
out of this repository:

1. **Developer ID certificate.** Keychain Access > My Certificates > "Developer ID Application:
   Berk Akbay (V88QY49A4T)" > right click > Export… as a `.p12` with a password. On the new Mac,
   double-click it. (Or create a new one in Xcode > Settings > Accounts > Manage Certificates.)
2. **Sparkle's private key** (signs every update; without it installed copies refuse updates):
   `build/sparkle/bin/generate_keys --account makara -x <file>` exports it; on the new Mac
   `generate_keys --account makara -f <file>` imports it (the tools come from
   `gh release download 2.10.0 --repo sparkle-project/Sparkle --pattern 'Sparkle-2.10.0.tar.xz'`).
   Its public half is `SUPublicEDKey` in the app's Info.plist.
3. **Notary profile:** run `xcrun notarytool store-credentials makara` again in Terminal (Apple
   ID, an app-specific password from account.apple.com, team `V88QY49A4T`).

Then: `scripts/release.sh <version>` (build, sign, notarize, DMG, appcast) and
`scripts/publish.sh [notes.md]` (release `v<version>` on xkbxyberk/makara-releases, latest). A new
runtime: `scripts/runtime/build_runtime.sh`, upload as `runtime-<version>` (`--latest=false`),
then copy its manifest into the Kit's Resources.
