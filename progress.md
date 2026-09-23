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

**Next:** M2 — download engine, queue and track picker.
