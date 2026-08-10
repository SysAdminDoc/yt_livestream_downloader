# Changelog

All notable changes to yt_livestream_downloader will be documented in this file.

## [v1.1.0] - 2026-08-03

- Added: overlap-aware segment capture with a two-writer pre-arm and clean boundary trim.
- Added: crash-resumable recording state and an atomic per-segment SHA-256 manifest.
- Added: quality fallback retries that step down through the configured ladder.
- Added: optional yt-dlp native fragment capture for DASH streams with an automatic ffmpeg fallback for unsupported HLS live streams.
- Added: optional Audio Only Super Chat capture with retained live-chat JSON and embedded `.m4a` chapters.
- Added: headless CLI parity for capture, resume, scheduling, subtitles, native fragments, Super Chat chapters, and disk thresholds.
- Added: JSON-backed sequential CLI queues with per-stream output, quality, schedule, and capture overrides.
- Added: credential-free channel watcher that polls yt-dlp's public `/live` listing and starts the shared recorder on detection.
- Added: dependency-free recurring five-field cron scheduling with bounded occurrence counts for headless capture.
- Added: optional Discord-compatible webhook notifications for saved segments, errors, clean stops, and stream completion.
- Added: GUI automatic-subtitle toggle with finalized sidecar renaming for overlap captures.
- Added: keyword-based live-chat chapter marks and preservation of yt-dlp-returned video chapters in `.ffmeta` files.
- Added: nonblocking GUI and headless post-process pipeline for concat, H.265, and two-pass loudnorm output.
- Added: periodic disk guardrails with configurable GUI thresholds and safe partial-segment pause/resume behavior.
- Added: optional input-free embedded mpv mini-player with graceful missing-dependency fallback.
- Added: persisted Mocha, Midnight, and Lavender theme variants with an application font-size override.
- Added: reproducible unsigned PyInstaller build with multiprocessing freeze support, runtime hook guard, and macOS/Linux packaging entry points.
- Added: deterministic WinGet and Scoop manifest generation with artifact SHA-256 pinning, plus a PyInstaller-backed Linux AppImage builder.
- Added: optional raw live-chat sidecars and post-session rclone uploads for completed segments.
- Added: normal-end numbered JPG thumbnail extraction and Audio Only silence-threshold trimming for final output utilities.
- Added: optional Streamlink capture backend with Auto routing for non-YouTube URLs, bounded ffmpeg muxing, GUI backend selection, and CLI guardrails for yt-dlp-only features.
- Fixed: frozen builds no longer recurse into themselves while bootstrapping optional dependencies.

## [v1.0.0] - Initial release

- Added: Add files via upload
- Added: Add files via upload

## Roadmap archive — 2026-08-10 — ROADMAP.md

<details>
<summary>Original roadmap snapshot</summary>

```markdown
# ROADMAP

YT Livestream Downloader is a PyQt6 desktop tool that records YouTube livestreams as sequential, timed segments using yt-dlp + ffmpeg. Catppuccin Mocha UI, scheduled start, auto-retry, crash logging.

## Planned Features

### Scheduling and automation

### Output

### UX

### Packaging

## Competitive Research

- **yt-dlp live-from-start** — Reference; this app is a thin GUI over it. Track their feature flags (native HLS segmenter, reconnect handling)
- **Streamlink** — Live-first CLI with deep stream-provider support; inspiration for the multi-platform future (not just YouTube)
- **OBS Studio recording** — Local-capture alternative; different niche but often used for the same need. Differentiation: no reliance on local playback
- **youtube-dl-gui / yt-dlp-gui** — Prior art for GUI wrappers; UX anti-patterns to avoid (modal-heavy, cluttered)

## Nice-to-Haves

## Open-Source Research (Round 2)

### Related OSS Projects
- https://github.com/Kethsar/ytarchive — Go-based YouTube livestream archiver that downloads from the first fragment (the gold-standard CLI)
- https://github.com/HoloArchivists/hoshinova — ytarchive manager: channel monitor + web UI + notifications on live-start/finish
- https://github.com/glubsy/livestream_saver — livestream downloader with cookie-based members-only stream support
- https://github.com/kubalisowski/YouTube-LiveStream-Archiver — multi-channel scheduler using YouTube Data API to detect live status
- https://github.com/Karan-Rabha/gui-stream-downloader — PyQt yt-dlp GUI with concurrent downloads and progress
- https://github.com/axcore/tartube — mature yt-dlp GUI (Gtk 3, not PyQt) with background livestream polling
- https://github.com/jely2002/youtube-dl-gui — Tauri + Vue cross-platform GUI, reference for a future Rust/Tauri rewrite
- https://github.com/ErrorFlynn/ytdlp-interface — native Win32 yt-dlp GUI, very small resource footprint
- https://github.com/yt-dlp/yt-dlp — upstream; review `--http-chunk-size`, `--keep-fragments`, `--buffer-size`, `--live-from-start`, `--wait-for-video`
- https://gist.github.com/glubsy/744d3f91b80347b3f684d3dc2fcb12e2 — "How to properly record YouTube & Twitch live streams" reference doc

### Features to Borrow
- Fragment-level download from stream start (not wall-clock start) via yt-dlp `--live-from-start` — already exposed by yt-dlp; surface as a GUI toggle
- Channel monitor: poll N channel URLs, auto-start recording when a stream goes live — hoshinova
- Members-only stream support via imported cookie jar (`--cookies cookies.txt` or browser cookie extraction with `--cookies-from-browser chrome`) — livestream_saver
- `--no-frag-files` in-memory fragment buffering for faster merges when disk I/O is the bottleneck — ytarchive
- Multi-thread fragment fetch (ytarchive `--threads N`) with a GUI-side warning about RAM cost when combined with `--no-frag-files`
- Web UI mode (Flask/FastAPI with a status page) as an alt to the PyQt GUI for headless/server deployments — hoshinova pattern
- Notification on stream-start + stream-finish (Windows toast / webhook / Discord) — hoshinova
- Schedule import: paste a YouTube "Upcoming" URL and auto-wait with `-w` + `--wait-for-video` — ytarchive
- Post-download auto-mux + thumbnail embed (`--embed-thumbnail --embed-metadata`) with fallback to ffmpeg CLI if yt-dlp postprocess fails — glubsy guide
- "Resume incomplete recording" button: detect `.part` + `.ytdl` files on startup and offer to continue — yt-dlp native behavior with GUI surfacing

### Patterns & Architectures Worth Studying
- ytarchive's fragment-aware retry: it re-asks YouTube for the same fragment number up to N times before giving up on the whole stream — port this retry semantic to yt-dlp-backed Python, since yt-dlp's `--fragment-retries` applies per-fragment but doesn't expose the same resumable-stream recovery
- Subprocess management: Popen with `stdout=PIPE, stderr=STDOUT, bufsize=1` + a reader `QThread` emitting `pyqtSignal(str)` per line → parses yt-dlp progress lines (`[download] 12.3% of ~5.00GiB...`) into a progress bar — Karan-Rabha/gui-stream-downloader does this; refine with a regex cache
- hoshinova's config schema (per-channel quality/path/output-template) in TOML — worth lifting as-is for your "multiple concurrent recordings" roadmap item
- livestream_saver's cookie-refresh loop (re-reads cookies.txt every N hours for long members-only streams that span token rotation) — essential for >12h recordings
- Tartube's scheduler-vs-recorder split into separate processes (IPC via file drop) — avoids GIL contention when both polling many channels and recording
```

</details>
