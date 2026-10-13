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

## 2026-09-23 — adversarial review of M2, and M3: library and settings

**The M2 review found 16 gaps; the reviewer reproduced most of them against the real code.**
All fixed, each with a regression test:
- **HIGH — a title of `..` wrote outside the download folder** (the `..` check ran before the
  extension was stripped). Naming now neutralises `.`/`..` from fields, refuses them in the
  template, trims components to 200 bytes, and claims a whole set of names atomically.
- **HIGH — cancel's delayed SIGKILL killed a retry started within 5 s**; the timer looked the
  job up by id. It is now bound to the process object and cancelled when that process exits.
- The concurrency limit could be exceeded, and a cancel lost, in the window before a worker
  process exists. Jobs are counted from the moment they are picked; a pending cancel is acted
  on as soon as the process appears. An exception inside `_run` no longer strands a job.
- The compatible-MP4 plan claimed "copy" for unknown codecs; it now says "probe" and warns.
  Audio-only mode states whether it copies or re-encodes.
- ⌘↵ worked from other screens and on key repeat; İndir could start on a plan computed for an
  older selection. Repeat separate-file downloads kept sidecars on the old base name. Audio mode
  ignored "keep cover as file". Unreadable subtitles (TTML) sank the whole job; they are now
  skipped with a warning. FFmpeg children could write into the event stream (`dup2`).

**Three bugs found by our own tests during M3:**
- The e2e suite caught the missing-file scan re-linking a deleted download to *another item's*
  byte-identical copy. Candidates owned by another item are now excluded.
- The e2e server log showed `sqlite3.InterfaceError` while every UI assertion passed: the
  library's connection was used from several threads. It now has its own connection and a lock;
  a test hammering it from 8 threads fails 7 of 8 without the lock. `check.sh` now fails on any
  server traceback during e2e, and verifies the log was actually captured.
- Audio items had no library thumbnail: an input seek to 0 drops the cover-art packet and
  FFmpeg exits 0 having written nothing. The worker test now asserts the thumbnail exists.

**A mistake in my own docs, corrected:** the README said to update yt-dlp with
`uv pip install -U`. `uv run` syncs the venv to `uv.lock` on every launch, so that update would
be silently reverted. The Doctor's button and all docs now upgrade the lock file.

**Test hygiene:** worker tests had been writing thumbnails into the real
`~/Library/Application Support/VideoDownloader`. That folder held only test artefacts (an empty
database and 82 `job<n>.jpg` files; the app had never been run for real) and was removed. An
autouse fixture now isolates every test, and the session fails if a real folder is touched.

**Not done, deliberately:** requeued jobs whose old worker survived a server crash are not killed
by pid (pid reuse could kill an unrelated process); the orphan dies on its broken pipe instead.

## 2026-09-23 (later) — M3 review, a real-world YouTube failure, and M4

**The M3 review** found three ways "Move to Trash" could trash *another item's* file (two missing
items re-linked to one file; a new file at an old path counted as "restored"; trashing an item
twice). Fixed with regression tests, plus Spotlight results from the Trash/backups ignored, tests
no longer querying the real Spotlight index, stricter download-folder validation, and a graceful
server shutdown when the desktop window closes.

**Berk's first real test failed** on https://www.youtube.com/watch?v=xnP7qKxwzjg with
"Site erişimi reddetti" (HTTP 403). Root cause was mine: the worker extracted with one
YoutubeDL, sanitized the info dict, and downloaded with another. YouTube URLs are signed lazily
at download time through callbacks that do not survive sanitize_info. Proven with a two-way
experiment (A: separate instances → 403; B: same instance → OK), fixed by extracting and
downloading in one instance per pass, and verified on that exact video and by the live tests.
The UI's advice ("update yt-dlp") was wrong for this case. Lesson recorded as CLAUDE.md gotcha 20:
the offline suite cannot see this class of bug; the live tests must be run after touching the
download path.

**M4 — Studio** (see SPEC "Stüdyo"). Found along the way: YouTube's rolling VTT cues start with
a line containing a single space, which a naive parser treats as the end of the cue and drops the
first sentence; stream-copy joins run a couple of frames long per piece (B-frames), which the
tests now state as an explicit bound instead of pretending otherwise.

**M4 review** (16 findings, most reproduced): keyframe predictions were wrong inside the first
GOP, false on audio with cover art, and blind to long GOPs and non-zero start times; an empty
output counted as success; joined lossless cuts broke on cover art; the preview differed from the
run (encoder, name); failed jobs left scratch next to Berk's file; Windows-1254 Turkish SRT files
were mangled; "/" in an output name made folders. All fixed with regression tests. It also found
that the download worker's separate side pass did its own extraction, which could fail the job
over subtitles alone and doubled the requests YouTube sees; side files now come from the single
stream pass (verified live with TR+EN subtitles). A transient-403 retry was added after live runs
showed YouTube refusing freshly signed URLs for a few minutes at a time.

**HIG redesign** (Berk's request, web path chosen over a SwiftUI rewrite so the tested backend
and e2e suite stay intact). New shell: source-list sidebar with symbols, unified toolbar with
per-screen actions via a portal, sun/moon/system theme picker, macOS semantic colors and control
styles, a Library inspector column, symbol buttons in the queue, status symbols in Sistem, real
sidebar vibrancy in the desktop window. The e2e tests changed only where the structure did (the
library's details moved from the card into the inspector); every assertion is kept. The narrow
screenshot run caught the floating sidebar covering the page after a resize; the sidebar now
collapses when the window gets narrow, like a Mac split view.

**Berk's first look at the redesign** (screenshots from the real window): he asked for animated
transitions, for the FFmpeg gaps to be filled, and reported help-tag bubbles clipped inside a
frame. The bubbles were absolutely positioned inside panels that clip their overflow; they are now
a portal with fixed positioning that flips above when there is no room (regression test at the
bottom edge of a narrow window). FFmpeg: with Berk's approval Homebrew's keg-only `ffmpeg-full`
was installed beside the plain build; the app prefers it (libass, libwebp, zimg all present,
doctor fully green, live downloads re-verified). Motion: sliding segmented thumbs, screen
fade-ins, sidebar collapse, sheet drop-down, inspector slide-in, theme cross-fade, press
feedback; all off under Reduce motion. Two e2e hover tests turned out to rely on timing (the page
shifts when the download plan arrives); they now wait for the page to settle. The e2e server
moved to port 8788 so it no longer collides with the running app.

**Plain ffmpeg removed** at Berk's request; ffmpeg-full linked onto PATH in its place (Homebrew
also auto-removed two libraries nothing used, libnghttp3 and libngtcp2). The next gate run hit a
1-in-4 e2e failure: a parallel test re-downloaded the same clip into a deleted file's freed name,
and the scan "restored" it into the old record. A real (rare) bug, fixed with a creation-time
rule and two regression tests that fail without it; 100 stressed e2e runs clean.

**Native track decided** (12 Oct): path B (SwiftUI screens over the same backend), Safari
extension with one-click downloads from the video's own choices (no fixed profiles, never
automatic). Plan N0–N8 in PLAN.md.

**N0 — spike, all four risks retired.** Project skeleton from Apple's packager (app + Safari web
extension), signed with Berk's team from `xcodebuild`. Safari kept the development-signed
extension enabled across three quit/reopen cycles (it even enabled it on first launch).
Round trip proven in the backend access log: `stage=ping` then `stage=report-ok`. A hand-added
XCUITest target launches the app, screenshots it, closes it and sees it quit; it now runs in
`scripts/check.sh`. Along the way the gate failed on 16 backend tests: a test clip had been
deleted from `tests/fixtures/media/` on 1 Oct; the fixture now rebuilds missing media.

**N1 — quick choices from the source.** `offers.py` builds one row per size/frame rate/range,
each resolved for MKV and MP4 with its size and copy-or-re-encode promise, plus audio-only rows;
`/api/quick` queues from a row or from a URL + remembered rule; `/api/supports` answers offline
in ~1 ms (generic extractor excluded, `kind` video/playlist/unknown); the web panel shows the
same rows and remembers the last clicked choice per site. The adversarial review found 11
real issues, all fixed with regression tests; the worst: an untouched default download saved
a rule, so a 240p-only video capped every later video from that site at 240p. Others: the
no-rule default ignored the MP4 output, an unknown audio language silently became the
original, audio re-encodes were not badged, a muxed file's size was shown as an audio size,
the MP4 360p row preferred a muxed baseline file over video + original audio.

**N2 — the SwiftUI app shell.** A real `VideoDownloader.app`: native sidebar (real vibrancy),
title bar, Turkish system menus, Git menu ⌘1–⌘5, Settings window, Dock badge, notifications,
`videodownloader://`, .webloc/Dock drops; the web UI shows embedded for every screen. The app
owns the backend (uv sync --frozen, venv python in its own process group, VD_PARENT_PID). The
pywebview launcher, desktop.py and pywebview are gone (pyobjc-framework-cocoa kept for the
clipboard watcher). Measured: a quit took 15.2 s (an open event stream blocked uvicorn until
the SIGKILL fallback, so the clean shutdown never ran), now 0.4 s. A UI-test screenshot was
taken of the whole screen and caught Berk's other windows; deleted, and only windows are shot
now. The adversarial review found 9 confirmed issues, all fixed with tests: a link handed to a
closed app was lost (calls raced the page load), workers survived a SIGKILLed server, an
attached server could die unnoticed, Retry started twice, a self-referencing .webloc crashed
the app, the Settings window could turn into another screen, plus stale badges, an English
error string and a 2 s wait on every quit.

**N3 — the Safari extension (built; live check pending).** Popup with the video's own choices
from `offers`, remembered per site, one click to the queue and live progress; icon from the
offline support check plus the page's own media; link menu; ⌃⇧D. The native half is a relay with
an allowlist (Relay.swift, 5 tests). The popup runs in the e2e suite against the real backend
with `browser.*` stubbed as a transport (7 tests). Not yet seen in Safari itself: Safari keeps
the old extension until it is restarted, and the new one needs "all websites" access from Berk;
I did not restart Safari while he was using it. Also fixed: `--print-extension-state` hung when
another copy of the app was running (it went through the backend shutdown path). The review
found 12 confirmed issues, all fixed with tests; the worst: the extension handler's shared
URLSession wrote every visited page address (tokens in query strings too) into an on-disk cache;
a remembered choice was lowered by any video that could not meet it (in the popup *and* the web
panel); a double click queued two downloads; the link menu could make the app fetch LAN or
loopback addresses. Also: wrong audio role labels, endless progress polling, "+" turning into a
space, a lost media flag when Safari unloads the background, unvalidated stored rules.

**N3 live check** (Berk asked me to restart Safari): Safari loaded the new extension; on the
test video the background script asked the app (3 support checks, all answered) and the button
read "Bu sayfadaki videoyu indir"; the popup, opened by a temporary UI test that was deleted
afterwards, showed the real choices (2160p … 144p AV1 with sizes). Nothing was downloaded. The
access log and the page dump (it held his YouTube recommendations) were deleted. Not yet seen
live: the link menu and ⌃⇧D.

**Next:** N4 — İndirmeler and Sistem in SwiftUI.
