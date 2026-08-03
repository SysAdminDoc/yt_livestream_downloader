# Changelog

All notable changes to yt_livestream_downloader will be documented in this file.

## [Unreleased]

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
- Fixed: frozen builds no longer recurse into themselves while bootstrapping optional dependencies.

## [v1.0.0] - %Y->- (HEAD -> main, origin/main, origin/HEAD)

- Added: Add files via upload
- Added: Add files via upload
