# Changelog

All notable changes to yt_livestream_downloader will be documented in this file.

## [Unreleased]

- Added: overlap-aware segment capture with a two-writer pre-arm and clean boundary trim.
- Added: crash-resumable recording state and an atomic per-segment SHA-256 manifest.
- Added: quality fallback retries that step down through the configured ladder.
- Added: optional yt-dlp native fragment capture for DASH streams with an automatic ffmpeg fallback for unsupported HLS live streams.
- Added: optional Audio Only Super Chat capture with retained live-chat JSON and embedded `.m4a` chapters.
- Fixed: frozen builds no longer recurse into themselves while bootstrapping optional dependencies.

## [v1.0.0] - %Y->- (HEAD -> main, origin/main, origin/HEAD)

- Added: Add files via upload
- Added: Add files via upload
