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
| Update yt-dlp | `uv lock --upgrade-package yt-dlp --upgrade-package yt-dlp-ejs && uv sync` (see gotcha 2) |
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
2. **Updating yt-dlp means updating `uv.lock`.** `yt-dlp -U` refuses pip/uv installs
   (`detect_variant()` is `"unknown"`), and `uv pip install -U` is silently reverted because
   `uv run` syncs the venv to the lock on every launch. Use
   `uv lock --upgrade-package yt-dlp --upgrade-package yt-dlp-ejs && uv sync` (the Doctor's
   button does exactly this). Nightly is not a separate PyPI package; it is a `.devN`
   pre-release of `yt-dlp` itself. Report versions from `importlib.metadata`, not the imported
   module, which is stale in the server after an update.
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
11. **We mux, not yt-dlp.** The worker downloads raw streams with `-f v,a1,a2` (comma) and
    `backend/app/ffmpeg/mux.py` builds the file. Do not "simplify" back to `+` and yt-dlp's
    merger: with several formats it re-fetches subtitles per format and reports a wrong subtitle
    `filepath`, and the multistreams semantics are slated to change upstream.
12. `-map_metadata -1` also drops chapter titles; see `mux.py` for the workaround.
13. The job manager's state is bound to the asyncio loop. Route handlers that touch it must be
    `async def`; never call it from a thread without `_on_loop`.
14. Offline download tests: `scripts/make_test_media.py` generates clips and `info.json`; the
    fixture URL `https://example.test/local-media` inspects them. The e2e server regenerates
    them and starts with an empty database on every run.
15. Scratch files live in `<download dir>/.vd-work/<job id>/` so a retry resumes `.part` files;
    only that directory is ever deleted, and only after the final file is in place.
16. **Filenames are untrusted input.** Use `naming.render_relative` + `naming.claim`: a title of
    `..` becomes `_`, components are trimmed to 200 bytes (APFS limit is 255), and a whole set
    of files gets one base name reserved atomically with O_EXCL placeholders. Never build an
    output path any other way.
17. **SQLite connections are not thread-safe.** The job store is used only on the event loop;
    the library has its own connection and a lock because it is also used from threads.
18. **Tests never touch Berk's folders.** An autouse fixture points `VD_DATA_DIR` and
    `VD_DOWNLOAD_DIR` at tmp dirs; fixture mode sends Trash to `simulated-trash`, and the
    folder picker and yt-dlp updater refuse to run. `scripts/check.sh` fails if the e2e server
    logged a traceback.
19. An FFmpeg input seek (`-ss`), even to 0, drops an audio file's single cover-art packet, and
    FFmpeg then exits 0 without writing anything. Check that outputs exist, not just exit codes.
20. **Never download from a sanitized/re-processed YouTube info dict.** Format URLs are finished
    lazily (the "n" JS challenge is solved at download time via callbacks sanitize_info drops),
    so extracting with one YoutubeDL and downloading with another gives HTTP 403 on every real
    YouTube video. Each pass calls `extract_info(url, download=True)` (see `_fetch`). The offline
    suite cannot catch this; run `RUN_LIVE_TESTS=1 uv run pytest -m live` after touching the
    download path.
21. Lossless (stream-copy) cuts start on the previous keyframe *and* can end a few frames late
    (B-frame reordering: 27 frames instead of 25 per 1 s piece at 25 fps). Tests state that bound;
    frame-accurate cuts are within one frame.

22. **Toolbar actions are portals.** A screen puts its toolbar buttons in
    `<ToolbarItems>` (`components/Toolbar.tsx`); they render into the window toolbar. Icons go
    through `<Icon name="sf.symbol.name">` (`components/Icon.tsx`) so the SF-style names stay in
    one map. An icon-only button needs an `aria-label` (the e2e tests find buttons by it).
23. The desktop window is `transparent=True, vibrancy=True` and loads `/?shell=native`; that CSS
    (`html.native`) only turns the sidebar see-through when the theme follows the system, since
    the material follows the system appearance, not ours.

## Rules

- **Never delete, skip, weaken or `xfail` a test to make the suite pass.** Fix the code.
- Studio operations write new files. Nothing overwrites or deletes the user's media without an
  explicit confirmation step in the UI, and deletes go to the Trash.
- Before any system-wide install (Homebrew, global npm), stop and ask Berk.
