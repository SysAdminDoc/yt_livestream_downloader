"""Headless command-line entry point for YT Livestream Downloader."""

from __future__ import annotations

import argparse
import json
import multiprocessing
import os
import signal
import shutil
import sys
from datetime import datetime
from pathlib import Path

from yt_livestream_core import APP_NAME, APP_VERSION, load_queue_items, load_session


DEFAULT_OUTPUT = Path.home() / "Downloads" / "YT_Livestreams"
QUALITY_CHOICES = ("Best", "1080p", "720p", "480p", "Audio Only")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="yt-livestream-downloader",
        description="Record a YouTube livestream as resilient, timestamped segments without opening the GUI.",
    )
    parser.add_argument("url", nargs="?", help="YouTube livestream URL")
    parser.add_argument("--queue-file", type=Path, help="JSON queue with one URL and optional per-stream overrides per item")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="Destination folder")
    parser.add_argument("--segment-minutes", type=int, default=30, metavar="N", help="Segment length (1-360 minutes)")
    parser.add_argument("--quality", choices=QUALITY_CHOICES, default="Best")
    parser.add_argument("--retries", type=int, default=3, metavar="N", help="Retry attempts per segment")
    parser.add_argument("--prefix", default="", help="Filename prefix; defaults to the stream title")
    parser.add_argument("--resume", action="store_true", help="Resume matching crash-resume state in the output folder")
    parser.add_argument("--native-fragments", action="store_true", help="Prefer yt-dlp native DASH fragment capture")
    parser.add_argument("--live-from-start", action="store_true", help="Ask yt-dlp to capture from the live stream start")
    parser.add_argument("--write-auto-sub", action="store_true", help="Write automatic subtitles beside each segment")
    parser.add_argument("--subtitle-languages", default="en.*", help="yt-dlp subtitle language selector")
    parser.add_argument("--superchat-chapters", action="store_true", help="Embed live-chat Super Chats as Audio Only chapters")
    parser.add_argument("--warn-free-gb", type=float, default=5.0, metavar="GB", help="Log a disk warning below this free space")
    parser.add_argument("--pause-free-gb", type=float, default=1.0, metavar="GB", help="Stop before recording below this free space")
    parser.add_argument("--start-at", metavar="DATETIME", help="Start at local ISO time, for example 2026-08-03T20:00:00")
    parser.add_argument("--version", action="version", version=f"{APP_NAME} {APP_VERSION}")
    return parser


def _parse_start_at(raw: str | None) -> datetime | None:
    if not raw:
        return None
    try:
        value = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"invalid --start-at value: {raw!r}; use ISO date/time") from exc
    if value.tzinfo is not None:
        value = value.astimezone().replace(tzinfo=None)
    return value


def _matching_resume_session(output_dir: Path, url: str):
    session = load_session(output_dir)
    if session is None:
        raise ValueError(f"no crash-resume state found in {output_dir}")
    if session.url != url:
        raise ValueError("crash-resume state belongs to a different URL")
    try:
        same_folder = Path(session.output_dir).resolve() == output_dir.resolve()
    except OSError:
        same_folder = session.output_dir == os.fspath(output_dir)
    if not same_folder:
        raise ValueError("crash-resume state belongs to a different output folder")
    return session


def _queue_namespace(base: argparse.Namespace, item: dict) -> argparse.Namespace:
    values = vars(base).copy()
    values["queue_file"] = None
    for key in (
        "output",
        "segment_minutes",
        "quality",
        "retries",
        "prefix",
        "resume",
        "native_fragments",
        "live_from_start",
        "write_auto_sub",
        "subtitle_languages",
        "superchat_chapters",
        "warn_free_gb",
        "pause_free_gb",
        "start_at",
    ):
        if key in item:
            values[key] = item[key]
    values["url"] = item["url"]
    return argparse.Namespace(**values)


def _run_queue(args: argparse.Namespace) -> int:
    try:
        items = load_queue_items(args.queue_file)
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
        print(f"error: cannot load queue file: {exc}", file=sys.stderr)
        return 2
    for index, item in enumerate(items, start=1):
        queued_args = _queue_namespace(args, item)
        print(f"Queue item {index}/{len(items)}: {queued_args.url}", flush=True)
        result = run(queued_args)
        if result:
            print(f"Queue stopped at item {index} with exit code {result}.", file=sys.stderr)
            return result
    print(f"Queue complete: {len(items)} stream(s).", flush=True)
    return 0


def run(args: argparse.Namespace) -> int:
    if args.queue_file:
        if args.url:
            print("error: provide either a URL or --queue-file, not both", file=sys.stderr)
            return 2
        return _run_queue(args)
    if not args.url:
        print("error: a URL is required unless --queue-file is provided", file=sys.stderr)
        return 2
    if not 1 <= args.segment_minutes <= 360:
        print("error: --segment-minutes must be between 1 and 360", file=sys.stderr)
        return 2
    if args.retries < 0:
        print("error: --retries cannot be negative", file=sys.stderr)
        return 2
    if args.warn_free_gb < 0 or args.pause_free_gb < 0 or args.pause_free_gb > args.warn_free_gb:
        print("error: disk thresholds must satisfy 0 <= pause-free-gb <= warn-free-gb", file=sys.stderr)
        return 2
    if args.superchat_chapters and args.quality != "Audio Only":
        print("error: --superchat-chapters requires --quality 'Audio Only'", file=sys.stderr)
        return 2

    try:
        start_at = _parse_start_at(args.start_at)
        resume_session = _matching_resume_session(args.output, args.url) if args.resume else None
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if not shutil.which("ffmpeg"):
        print("error: ffmpeg is required and must be available on PATH", file=sys.stderr)
        return 2

    from PyQt6.QtCore import QCoreApplication, QTimer

    from yt_livestream_downloader import SegmentDownloader

    app = QCoreApplication(sys.argv)
    holder = {"worker": None, "exit_code": 0, "timer": None}

    def stop_handler(_signum, _frame):
        worker = holder["worker"]
        if worker is None:
            print("Stopping before the scheduled start...", flush=True)
            app.quit()
        else:
            print("Stopping after active captures finalize...", flush=True)
            worker.request_stop()

    def start_worker():
        worker = SegmentDownloader(
            url=args.url,
            output_dir=os.fspath(args.output),
            segment_minutes=args.segment_minutes,
            quality=args.quality,
            max_retries=args.retries,
            filename_prefix=args.prefix,
            resume_session=resume_session,
            live_from_start=args.live_from_start,
            use_native_segmenter=args.native_fragments,
            write_subtitles=args.write_auto_sub,
            subtitle_languages=args.subtitle_languages,
            capture_superchats=args.superchat_chapters,
            warn_free_gb=args.warn_free_gb,
            pause_free_gb=args.pause_free_gb,
        )
        holder["worker"] = worker
        worker.log_message.connect(lambda message: print(message, flush=True))
        worker.status_update.connect(lambda message: print(f"[status] {message}", flush=True))
        worker.segment_complete.connect(
            lambda filepath, size: print(f"[saved] {filepath} ({size / (1024 * 1024):.1f} MB)", flush=True)
        )
        worker.error.connect(lambda message: (print(message, file=sys.stderr, flush=True), holder.__setitem__("exit_code", 1)))
        worker.finished_all.connect(app.quit)
        worker.start()

    signal.signal(signal.SIGINT, stop_handler)
    signal.signal(signal.SIGTERM, stop_handler)

    if start_at is not None:
        delay_ms = max(0, int((start_at - datetime.now()).total_seconds() * 1000))
        if delay_ms:
            print(f"Scheduled start: {start_at.isoformat(sep=' ', timespec='seconds')}", flush=True)
            timer = QTimer()
            timer.setSingleShot(True)
            timer.timeout.connect(start_worker)
            timer.start(delay_ms)
            holder["timer"] = timer
        else:
            start_worker()
    else:
        start_worker()

    exit_code = app.exec()
    worker = holder["worker"]
    if worker is not None and worker.isRunning():
        worker.request_stop()
        worker.wait(10000)
    return holder["exit_code"] or exit_code


def main() -> int:
    multiprocessing.freeze_support()
    parser = build_parser()
    return run(parser.parse_args())


if __name__ == "__main__":
    raise SystemExit(main())
