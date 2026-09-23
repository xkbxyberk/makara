# VideoDownloader — notes for a future session

Local-only media workstation on yt-dlp + FFmpeg. macOS arm64, single user (Berk).
**Talk to Berk in Turkish. Code, comments, commits and docs in English.**
**Every user-facing string lives in `frontend/src/i18n/tr.ts` and nowhere else.**

## Commands

| What | Command |
|---|---|
| The gate (lint, types, pytest, vitest, build, e2e) | `./scripts/check.sh` |
| Backend tests only | `uv run pytest -q` |
| Frontend unit tests | `cd frontend && npx vitest run` |
| End-to-end + screenshots | `cd frontend && npx playwright test` |
| Dev servers | `PYTHONPATH=backend uv run python -m app.main` + `cd frontend && npm run dev` |
| Desktop app | `open VideoDownloader.command` |
| Update yt-dlp | `uv pip install -U "yt-dlp[default]"` (see gotcha 2) |
| Re-record fixtures (network!) | `uv run python scripts/capture_fixtures.py [name ...]` |

## Architecture decisions

- **FastAPI on 127.0.0.1:8787**, serving `frontend/dist` as an SPA. Never bind anything else.
- **Every yt-dlp/FFmpeg job runs in its own child process.** Cancel means kill the child; a
  crash cannot take the server down. Worker protocol: one JSON request on stdin, one JSON
  response (later: JSONL progress) on stdout. `shell=True` appears nowhere.
- **`backend/app/ytdlp/normalize.py` is the heart.** Every screen consumes its output and
  every test asserts against it. Change it deliberately.
- **Backend never returns Turkish.** `errors.py` produces stable codes; `tr.ts` renders them.
- **Tests never touch the network.** They read `tests/fixtures/infojson/*.json`, recorded once
  from the real sites. The e2e suite runs the real server with `VD_FIXTURE_MODE=1`.
- Frontend is plain React + hand-written CSS variables. No UI framework, no router, no state
  library — the app is too small to earn them.

## Gotchas that will bite you

1. **JS runtime.** Modern YouTube needs `yt-dlp-ejs` (ships with `yt-dlp[default]`) *and* a
   JavaScript engine. The `YoutubeDL` key is the top-level **`js_runtimes`**, and passing a
   dict *replaces* the deno-only default. Without a runtime yt-dlp does **not** fail — it
   silently drops the `web` client and some formats vanish. Deno 2.9.7 is installed here.
2. **`yt-dlp -U` does not work for pip/uv installs** (`detect_variant()` returns `"unknown"`).
   Update by rerunning the install. Nightly is *not* a separate PyPI package; it is a `.devN`
   pre-release of `yt-dlp` itself (`--pre` / `--prerelease=allow`).
3. **YouTube splits subtitles three ways, not two.** `subtitles` = human. `automatic_captions`
   mixes the ASR track for the spoken language (key has an `-orig` twin, or URL has `kind=asr`)
   with hundreds of machine translations (URL has `tlang=`, or the name reads "X from Y").
   `live_chat` is a fake language key inside `subtitles` — always filter it out.
4. **yt-dlp cannot tell a human dub from an AI auto-dub.** There is no field. The only signal
   is `language_preference` (10 original, 5 default, -10 audio description, else dub). Do not
   invent an "auto-dub" badge; the UI says "Dublaj" and the tooltip explains the limit.
5. **`vcodec`/`acodec` use the string `"none"` as a sentinel; `None` means unknown.**
   archive.org returns `None` for both on real video files.
6. **Sizes have three tiers** (`filesize`, `filesize_approx`, `tbr * duration`). For HLS/DASH
   formats `tbr` is often the *peak* bitrate, so those estimates read high — the model flags
   them with `filesize_unreliable` and the UI must keep saying so.
7. **This FFmpeg build has no libass and no libwebp.** Burning subtitles into the picture and
   animated WebP output are therefore impossible. The doctor detects this at runtime; never
   ship a feature that assumes them.
8. **Lossless vs frame-accurate cuts** (for M4): stream-copy cuts land on keyframes and will
   drift by up to a GOP; frame-accurate cuts require re-encoding. The UI must offer both and
   explain the trade-off, never silently pick one.
9. `format_id` values are de-duplicated by yt-dlp (`140-0`, `251-drc`, `247-sr`). Always key on
   the final `format_id` string, never a raw itag.
10. Playwright specs are `frontend/e2e/*.spec.cts` (`.cts`, because the package is ESM and
    `@playwright/test` is CommonJS). Screenshots land in `test-results/screenshots/`.

## Rules

- **Never delete, skip, weaken or `xfail` a test to make the suite pass.** Fix the code.
- Studio operations write new files. Nothing overwrites or deletes the user's media without an
  explicit confirmation step in the UI, and deletes go to the Trash.
- Before any system-wide install (Homebrew, global npm), stop and ask Berk.
