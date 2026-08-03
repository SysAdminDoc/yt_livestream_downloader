# YT Livestream Downloader

![Version](https://img.shields.io/badge/version-1.0.0-blue)
![Python](https://img.shields.io/badge/Python-3.8+-3776AB?logo=python&logoColor=white)
![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey)
![License](https://img.shields.io/badge/license-MIT-green)

> A desktop GUI tool that records YouTube livestreams in timed segments, saving each chunk as a separate file. Built with PyQt6 and powered by yt-dlp + ffmpeg.

![Screenshot](screenshot.png)

## Quick Start

```bash
git clone https://github.com/YOUR_USERNAME/yt-livestream-downloader.git
cd yt-livestream-downloader
python yt_livestream_downloader.py
```

PyQt6 and yt-dlp are auto-installed on first run. The only external dependency you need pre-installed is **ffmpeg**.

For the packaged Windows executable, install the **yt-dlp command-line tool** on `PATH` before launching; frozen builds do not run pip or ensurepip.

## Features

| Feature | Description |
|---------|-------------|
| **Segmented Recording** | Records livestreams in configurable time chunks (1-360 min, default 30 min) with a pre-armed overlap to reduce boundary gaps |
| **Quality Selection** | Best, 1080p, 720p, 480p, or Audio Only |
| **Auto-Retry** | Configurable retry attempts per segment, with automatic reconnection and quality fallback on network or format failures |
| **Disk Guardrails** | Periodic free-space checks warn at the configured threshold and finalize/pause safely at the lower threshold for crash-resume continuation |
| **Scheduled Start** | Set a future date/time to automatically begin recording |
| **Stream Info Preview** | Fetch and display stream title + live status before recording |
| **Live Stats Dashboard** | Real-time segment count, total size, elapsed time, and status cards |
| **Toast Notifications** | In-app notification when each segment completes |
| **Segment Playback** | Double-click any recorded segment to open in your default media player |
| **Persistent Settings** | Remembers output folder, quality, segment length, retries, and last URL between sessions |
| **Crash Resume** | Persists the next segment and offers to resume an interrupted recording when the same URL and folder are opened again |
| **Integrity Manifest** | Writes an atomic `.yt_livestream_manifest.json` with each segment's size, SHA-256 checksum, quality, and partial status |
| **Native DASH Capture** | Optional yt-dlp native fragment mode for DASH streams; automatically falls back to ffmpeg when a provider exposes an unsupported HLS live stream |
| **Super Chat Chapters** | Optional Audio Only mode captures YouTube live-chat paid messages, keeps the JSON sidecar, and embeds them as chapters in `.m4a` segments |
| **Headless CLI** | Runs the same recorder without a window for NAS/server use, including resume, scheduling, subtitles, native fragments, and disk thresholds |
| **Channel Watcher** | Polls a channel's public `/live` page and starts the recorder when yt-dlp reports a live video |
| **Webhook Notifications** | CLI can POST Discord-compatible segment, error, stop, and stream-end events to one or more webhook URLs |
| **Automatic Subtitles** | Optional yt-dlp automatic subtitle capture is kept as a companion sidecar beside each finalized segment |
| **Chapter Marks** | Matching live-chat keywords and yt-dlp-returned video chapters are preserved as an `.ffmeta` chapter-mark file; Audio Only can embed them |
| **Post-process Pipeline** | Optional normal-end concat, H.265 transcode, and two-pass -16 LUFS loudnorm run off the GUI or CLI without changing the original segments |
| **Embedded Mini-player** | Optional mpv surface inside the GUI for live preview; missing mpv disables only the preview |
| **Theme + Font Controls** | Persisted Mocha, Midnight, or Lavender palette with a 10-22 px application font override |
| **Dependency Validation** | Startup check for yt-dlp and ffmpeg with version display |
| **Crash Logging** | Writes `crash.log` on unhandled exceptions for debugging |
| **Dark Theme** | Catppuccin Mocha dark interface |

## Prerequisites

| Requirement | Notes |
|-------------|-------|
| **Python 3.8+** | [python.org](https://www.python.org/downloads/) |
| **ffmpeg** | Must be on your system PATH |
| **yt-dlp** | Auto-installed via pip if missing |
| **PyQt6** | Auto-installed via pip if missing |
| **mpv** | Optional; place `mpv` on PATH to enable the embedded mini-player |

### Installing ffmpeg

**Windows:** Download from [gyan.dev/ffmpeg/builds](https://www.gyan.dev/ffmpeg/builds/) (get the `essentials` build), extract, and add the `bin` folder to your system PATH.

**macOS:**
```bash
brew install ffmpeg
```

**Linux (Debian/Ubuntu):**
```bash
sudo apt install ffmpeg
```

### JavaScript Runtime (Recommended)

Recent versions of yt-dlp recommend a JavaScript runtime for YouTube extraction. Install **deno** for best results:

**Windows:**
```powershell
irm https://deno.land/install.ps1 | iex
```

**macOS/Linux:**
```bash
curl -fsSL https://deno.land/install.sh | sh
```

Without a JS runtime, yt-dlp may display a warning and some formats could be unavailable.

## Usage

1. **Launch** the app: `python yt_livestream_downloader.py`
2. **Paste** a YouTube livestream URL
3. **(Optional)** Click **Fetch Info** to verify the stream is live
4. **Configure** segment length, quality, and output folder as needed
5. For **Audio Only**, optionally enable **Super Chat chapters** to retain paid-message timestamps as embedded chapters
6. Optionally enable **Automatic subtitles** to write subtitle sidecars beside each segment
7. Optionally enter comma-separated **Chat chapter keywords** such as `milestone, giveaway`
8. Click **Start Recording** — segments save automatically as `StreamTitle_seg001_TIMESTAMP.mp4`
9. Click **Stop** at any time — the current partial segment is saved
10. **Double-click** any segment in the list to play it

### Headless CLI

The headless entry point uses the same segmented recorder and never creates a window:

```bash
python yt_livestream_cli.py "https://www.youtube.com/watch?v=..." \
  --output ./captures --segment-minutes 30 --quality "Audio Only" \
  --resume --superchat-chapters
```

Use `python yt_livestream_cli.py --help` for the complete option list. `--start-at` accepts a local ISO timestamp, and `Ctrl+C` requests a clean partial-segment finalization.

For sequential multi-stream capture, pass a JSON queue. Items may override the shared CLI defaults with `output`, `start_at`, `quality`, `segment_minutes`, `retries`, and capture flags:

```json
{
  "items": [
    {"url": "https://www.youtube.com/watch?v=first", "start_at": "2026-08-03T20:00:00"},
    {"url": "https://www.youtube.com/watch?v=second", "quality": "Audio Only", "superchat_chapters": true}
  ]
}
```

Run it with `python yt_livestream_cli.py --queue-file queue.json`. The queue advances only after the current stream exits successfully; a failed item stops the queue and returns its non-zero exit code.

To wait for a channel to go live, use `python yt_livestream_cli.py --watch-channel https://www.youtube.com/@creator --poll-seconds 60`. Add `--watch-timeout 3600` for a bounded wait; omit it to keep watching until interrupted.

For recurring captures, pass a standard five-field local cron expression, such as `python yt_livestream_cli.py URL --cron "0 20 * * 2" --cron-count 4`. Leave `--cron-count` at its default `0` to continue indefinitely; each occurrence runs through the normal retry, resume, manifest, and disk-safety paths.

Add `--webhook-url https://...` to receive notifications. Repeat the option for multiple endpoints; delivery failures are logged as warnings and never interrupt recording. Use `--chapter-keyword milestone` (repeatable) for the same keyword chapter marks in headless mode.

Use `--concat` to join completed segments at normal stream end, `--h265` to produce a libx265 video output, and `--loudnorm` to run measured two-pass normalization. The GUI exposes the same choices. Original segment files and their manifest remain unchanged.

Enable **Embedded mpv mini-player** in the GUI to preview the stream inside the app. It is optional and does not affect capture when mpv is unavailable.

Choose **Theme** and **Font size** in Stream Settings; the selection is applied immediately and saved with the other preferences.

If a session is interrupted, reopen the same URL and output folder and leave **Resume previous session** enabled to continue at the next segment recorded in the session state.

### Scheduled Recording

Check **Scheduled Start**, set a date/time, and click Start. The app will wait with a countdown timer and begin recording automatically when the time arrives.

### Output Files

Files are saved to `~/Downloads/YT_Livestreams` by default. Each segment is a standalone `.mp4` (or `.m4a` for audio-only) file named:

```
Stream_Title_seg001_20260208_230333.mp4
Stream_Title_seg002_20260208_233333.mp4
Stream_Title_seg003_20260209_000333.mp4
```

The output folder also contains a crash-resume state file and an atomic `.yt_livestream_manifest.json` checksum manifest. The manifest is updated after each finalized segment, including user-stopped partial captures. When Super Chat chapters are enabled, the raw live-chat capture remains beside the audio segments as `<stream>.live_chat.json`.

## How It Works

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│   YouTube URL    │────>│     yt-dlp      │────>│  ffmpeg -t Ns   │
│                  │     │                 │     │                 │
│  Paste stream    │     │  Resolves live  │     │  Records for N  │
│  URL into GUI    │     │  stream formats │     │  seconds, saves │
│                  │     │  & passes to    │     │  as .mp4 file   │
│                  │     │  ffmpeg         │     │                 │
└─────────────────┘     └─────────────────┘     └────────┬────────┘
                                                         │
                                              Segment complete?
                                                         │
                                                    ┌────▼────┐
                                                    │  Loop:  │
                                                    │  Start  │
                                                    │  next   │
                                                    │ segment │
                                                    └─────────┘
```

Each segment launches a fresh yt-dlp process with `--downloader ffmpeg` and `--downloader-args "ffmpeg:-t <seconds>"`. The next writer is pre-armed before the boundary, and its overlap prefix is stream-copy trimmed so finalized segments stay contiguous while preserving independent files. Native DASH mode uses yt-dlp's fragment downloader and falls back to the same ffmpeg path when native capture cannot handle the stream.

Auto-retry handles transient network failures. After 3 consecutive segment failures, the app assumes the stream has ended and stops.

## Configuration

Settings are persisted to:

| OS | Location |
|----|----------|
| Windows | `%APPDATA%\YTLivestreamDL\config.json` |
| macOS/Linux | `~/YTLivestreamDL/config.json` |

Saved fields: output directory, segment length, quality preset, retry count, native fragment preference, Super Chat chapter preference, automatic subtitle preference, last URL.

## Troubleshooting

| Issue | Solution |
|-------|----------|
| `ffmpeg: NOT FOUND` in header | Install ffmpeg and add to PATH. Restart the app. |
| `yt-dlp: NOT FOUND` in header | Run `pip install yt-dlp` or let the app auto-install on next launch. |
| Packaged build cannot find yt-dlp | Install the yt-dlp command-line executable and make sure it is on `PATH`; packaged builds do not self-install Python packages. |
| `Requested format is not available` | Change quality from a specific resolution to "Best" — livestreams have limited format options. |
| JS runtime warning | Install deno (see Prerequisites). Not strictly required but recommended. |
| Segments are empty / 0 bytes | The stream may have ended, or the URL is not a live stream. Use **Fetch Info** to check. |
| Gaps between segments | The recorder pre-arms the next writer and trims its overlap prefix. If a provider still exposes a discontinuity, check the activity log for retry or fallback messages. |
| Super Chat chapters are missing | Chapters require **Audio Only**, a live-chat stream exposed by YouTube, and ffmpeg. The `.live_chat.json` sidecar is retained so the capture can be inspected independently. |
| App freezes on close | The app waits up to 5 seconds for the current download to terminate. If it persists, force-close. |

## License

MIT License - see [LICENSE](LICENSE) for details.

## Contributing

Issues and PRs welcome. If you find a bug or have a feature request, please open an issue.
