# Session notes

## 2026-09-23 — Phase 0, Phase 1, M0 and M1

**Reconnaissance corrected three things in the brief.**
- **Deno 2.9.7 is installed** (`/opt/homebrew/bin/deno`); the brief said it was not. No Homebrew
  install was needed. Node 26.9 is present as a second runtime. pnpm and bun are absent.
- **`yt-dlp[default]` now ships `yt-dlp-ejs==0.8.0`**, so the EJS scripts come with the install;
  only the JS engine itself is external. `js_runtimes` is a top-level `YoutubeDL` param and a
  dict *replaces* the deno-only default.
- **There is no `yt-dlp-nightly-builds` package on PyPI** (404). Nightly is a `.devN`
  pre-release of `yt-dlp` itself. `yt-dlp -U` does not work for pip/uv installs at all.
- Machine: macOS 27.0, Apple M4, 16 GB, 96 GB free. FFmpeg 9.0.2 with libx264/265/SVT-AV1,
  VideoToolbox, loudnorm, palettegen — but **no libass and no libwebp**.

**Fixture capture.** Vimeo now demands a login even for its own demo clips, so the non-YouTube
fixture is archive.org instead. The many-subtitle fixture came back at **16 MiB**: that video
has 64 manual languages and **10147** `automatic_captions` keys x 8 formats. It was trimmed to
323 keys and 3 formats per track, recorded in the file's `_fixture_note` and in
`tests/fixtures/infojson/README.md`.

**Two findings that changed the design.**
1. yt-dlp has no field separating a human dub from an AI auto-dub — zero matches for
   `dubbed`/`autodub` in the extractor. The catalogue asked for an "auto-dubbed" badge; that
   badge cannot be truthful, so the UI says "Dublaj" and the tooltip explains the limit.
2. The brief's "subtitles vs automatic_captions" split is too coarse. Machine translations
   sourced from *manual* tracks also land in `automatic_captions`, which is where the 10147
   keys come from. Classification therefore reads the URL query (`kind=asr` vs `tlang=`) and
   the `-orig` suffix, not just which dictionary a key came from.

**Deviations from the approved plan, and why.**
- Inspect uses a plain `POST` rather than SSE. SSE buys nothing for a single request/response;
  the infrastructure belongs with job progress in M2. The loading state is unaffected.
- SQLAlchemy is installed but unused until M3 — no tables exist yet, on purpose.
- Playwright specs live in `frontend/e2e/*.spec.cts` rather than `tests/e2e/`: the frontend
  package is ESM and `@playwright/test` is CommonJS, and the specs must resolve
  `node_modules` from the frontend package. Screenshots go to `test-results/screenshots/`.
- The venv resolved to Python 3.13 rather than 3.12. Everything passes; `requires-python` is
  `>=3.12`, so this is fine.

**Screenshot review.** Five fixes came out of actually looking at the output: SF Symbol
codepoints do not render in the webview (glyphs removed), the narrow layout was hiding the
Size column (now hides HDR/bitrate/container instead), the metadata thumbnail collapsed to
zero height before loading, the theme toggle mislabelled itself under "system", and the
per-check doctor badges reused the global status wording.

## 2026-09-23 (later) — adversarial review of M0+M1

A fresh-context reviewer found 17 gaps. The M1 criteria had been marked passing on the strength
of tests that were too weak to catch them, which is the lesson worth keeping. All fixed, each with
a regression test:

- **Every extraction error became "Video yok".** `ignoreerrors="only_download"` is truthy, so
  yt-dlp *reported* extractor errors and returned `None`. Now `False`; the worker also collects
  yt-dlp's log through a `logger` so the raw tail reaches the UI.
- **Shell injection through the copyable command.** `quote()` did not escape `'`. Now
  `shlex.join`, tested by round-tripping hostile URLs through `shlex.split`.
- **Playlists were extracted in full** (a channel would time out). Inspect is always
  `extract_flat="in_playlist"` with `noplaylist=True`.
- **6 of 8 "auto" subtitles were machine translations** delivered as bare HLS playlists without
  `tlang=`. Auto-generated now means exactly the spoken language (from the `-orig` key).
- Missing JS runtime / signature-solving warnings are now surfaced as model warnings.
- More precise error codes: `BOT_CHECK` (YouTube's "confirm you're not a bot" is not a login
  problem), `RATE_LIMITED`, `FORBIDDEN`, HTTP 404 → unavailable.
- Host-header allowlist (DNS rebinding) and a cross-site request guard for non-GET methods.
- Inspect child runs in its own process group and is killed in a `finally`; garbage stdout
  becomes `UNKNOWN` with the stderr tail instead of an HTTP 500.
- Frontend: remaining hardcoded strings moved to `tr.ts`; every technical column header and
  codec now has a tooltip; a slow earlier inspect can no longer overwrite a newer one.
- `multi_video` renders as a list; `vcodec` known + `acodec` None is no longer called "ses dahil";
  a size total with an unknown part is labelled a lower bound (`≥`).
- Also found while starting M2: YouTube's AI-upscaled (`-sr`) formats. For the TED fixture the
  real source is 240p and every 360p–720p option is upscaled. They are now badged, and the
  archive default picks the original.

## 2026-09-23 — M2: download engine, queue, track picker

**The key design decision: yt-dlp downloads, we mux.** yt-dlp fetches each selected format as
its own raw file (`-f v,a1,a2` with a comma, not `+`), then our own FFmpeg command builds the
output. That makes language tags, the default flag, subtitle codecs and copy-vs-transcode
explicit and decided by *probing the real files*, and it isolates us from the multistreams
behaviour the README says will change. A spike showed why this was necessary: with several
formats, yt-dlp re-downloads subtitles for every one of them, and the `filepath` it reports in
`requested_subtitles` is wrong (it names the last stream, not the file it wrote).

**Offline downloads.** `scripts/make_test_media.py` generates clips with `testsrc2`/`sine` and a
synthetic info dict whose URLs point at 127.0.0.1. Tests run the real yt-dlp downloader and real
FFmpeg against them, and verify every output with `ffprobe`. A throttled, Range-capable test
endpoint lets a test cancel mid-download and prove the retry *resumed*.

**Bugs the tests caught on the way:**
- FastAPI runs sync handlers in a threadpool, but the queue's `asyncio.Queue`/`Event` are
  loop-bound and not thread-safe. Handlers that touch the manager are `async` now, and the
  manager marshals any off-loop call with `call_soon_threadsafe`.
- `-map_metadata -1` also strips chapter titles. With chapters, the (tag-less) ffmetadata file
  is used as the metadata source instead.
- Matroska surfaces an attachment named `cover.jpg` as an attached-picture video stream; that
  is correct (players show it), tests now expect it.
- TestClient never delivers an HTTP disconnect to a streaming response, so the SSE test runs
  against a real uvicorn server; the manager also sends a shutdown event so open streams never
  hold up server shutdown.

**Deviations from the plan:** SQLAlchemy was dropped in favour of plain `sqlite3` — one small
table does not earn an ORM. The Settings *screen* moves to M3 (its API exists).

**Next:** adversarial review of M2, then M3 — Library and Settings.
