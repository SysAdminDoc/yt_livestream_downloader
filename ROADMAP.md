# ROADMAP

YT Livestream Downloader is a PyQt6 desktop tool that records YouTube livestreams as sequential, timed segments using yt-dlp + ffmpeg. Catppuccin Mocha UI, scheduled start, auto-retry, crash logging.

## Planned Features

### Recording engine
- Eliminate the 2-5s gap between segments — run two overlapping ffmpeg writers with the second pre-arming at `N-2s`, then truncate cleanly at boundary
- HLS / DASH direct capture path that bypasses ffmpeg's `-t` segmentation and uses yt-dlp's native segmenter
- Resume-on-crash: persist the current URL, segment index, and target folder so a relaunch picks up where it left off
- Per-segment checksums written to a `.manifest.json` for integrity verification
- Audio-only `.m4a` with embedded chapters from live-chat "superchat" timestamps (fun bonus)

### Scheduling and automation
- Multi-stream queue with per-stream schedule (today it's one URL at a time)
- "Watch channel" mode — poll a channel's live tab and auto-start when they go live
- Cron-style recurring schedule (e.g., every Tuesday 8pm)
- Webhook / Discord notifications on segment-complete and stream-end
- CLI parity — same options as the GUI, runnable headless on a NAS

### Output
- Post-process pipeline: optional auto-concat of segments at stream end, optional transcode to H.265, optional two-pass loudnorm
- Chapter-mark file from stream's live-chat "milestone" keywords or from yt-dlp's returned video chapters
- Automatic subtitle grab (`--write-auto-sub`) as a companion `.vtt` per segment

### UX
- Mini-player panel (mpv-embedded) to watch live during recording without opening a separate app
- Quality fallback ladder — if 1080p format disappears mid-stream, re-probe and step down instead of failing
- Disk-space guardrails: warn at N GB free, auto-pause at M GB free
- Theme picker (Catppuccin variants) and font size override

### Packaging
- PyInstaller single-exe build with the mandatory `multiprocessing.freeze_support()` + runtime hook guards (see `~/.claude/CLAUDE.md` PyInstaller section)
- Winget + Scoop manifests
- macOS `.app` via `py2app`, Linux AppImage

## Competitive Research

- **yt-dlp live-from-start** — Reference; this app is a thin GUI over it. Track their feature flags (native HLS segmenter, reconnect handling)
- **Streamlink** — Live-first CLI with deep stream-provider support; inspiration for the multi-platform future (not just YouTube)
- **OBS Studio recording** — Local-capture alternative; different niche but often used for the same need. Differentiation: no reliance on local playback
- **youtube-dl-gui / yt-dlp-gui** — Prior art for GUI wrappers; UX anti-patterns to avoid (modal-heavy, cluttered)

## Nice-to-Haves

- Twitch and Kick support (Streamlink as backend when the URL is non-YouTube)
- Auto-upload completed recordings to a rclone remote (Drive, B2, S3)
- Thumbnail extraction every N seconds for a later contact-sheet
- Live chat log capture as a side `.json` file
- "Silence skip" post-process — auto-cut dead air longer than X seconds from final concat

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
