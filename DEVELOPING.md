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
   - Safari > Settings > Extensions: turn on Makara and allow it on all websites (restart Safari
     after every rebuild of the extension).
   - System Settings > Privacy & Security > Full Disk Access: Makara, if downloads should use the
     Safari session (CLAUDE.md gotcha 36).
   - Sign in to YouTube, Reddit, Instagram and X in Safari again.
6. **Check it:** `./scripts/check.sh` (the full gate; it opens the app window for UI tests).

Not in git, restore from a backup if wanted: the downloads (`~/Movies/VideoDownloader`), the
catalogue and settings (`~/Library/Application Support/VideoDownloader`), and Claude's notes for
this project (`~/.claude/projects/-Users-akbay-VideoDownloader/`).
