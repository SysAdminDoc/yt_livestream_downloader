"""Headless command-line entry point for YT Livestream Downloader."""

from __future__ import annotations

import argparse
import json
import multiprocessing
import os
import signal
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

from yt_livestream_core import (
    APP_NAME,
    APP_VERSION,
    build_channel_watch_command,
    load_queue_items,
    load_session,
    next_cron_datetime,
    parse_channel_live_result,
)


DEFAULT_OUTPUT = Path.home() / "Downloads" / "YT_Livestreams"
QUALITY_CHOICES = ("Best", "1080p", "720p", "480p", "Audio Only")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="yt-livestream-downloader",
        description="Record a YouTube livestream as resilient, timestamped segments without opening the GUI.",
    )
    parser.add_argument("url", nargs="?", help="YouTube livestream URL")
    parser.add_argument("--queue-file", type=Path, help="JSON queue with one URL and optional per-stream overrides per item")
    parser.add_argument("--watch-channel", help="Poll a public channel URL until a live video appears")
    parser.add_argument("--poll-seconds", type=int, default=60, metavar="N", help="Channel poll interval")
    parser.add_argument("--watch-timeout", type=int, default=0, metavar="N", help="Stop watching after N seconds (0 means forever)")
    parser.add_argument("--cron", metavar="EXPR", help="Recurring five-field local cron schedule")
    parser.add_argument("--cron-count", type=int, default=0, metavar="N", help="Number of cron occurrences (0 means forever)")
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


def _watch_ytdlp_command() -> list[str]:
    path = shutil.which("yt-dlp")
    return [path] if path else [sys.executable, "-m", "yt_dlp"]


def _run_watch(args: argparse.Namespace) -> int:
    if args.poll_seconds < 5:
        print("error: --poll-seconds must be at least 5", file=sys.stderr)
        return 2
    if args.watch_timeout < 0:
        print("error: --watch-timeout cannot be negative", file=sys.stderr)
        return 2
    command = _watch_ytdlp_command()
    deadline = time.monotonic() + args.watch_timeout if args.watch_timeout else None
    print(f"Watching {args.watch_channel} for a live stream...", flush=True)
    while deadline is None or time.monotonic() < deadline:
        try:
            result = subprocess.run(
                build_channel_watch_command(command, args.watch_channel),
                capture_output=True,
                text=True,
                timeout=min(60, max(10, args.poll_seconds)),
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            if result.returncode == 0 and result.stdout.strip():
                live_url = parse_channel_live_result(result.stdout)
                if live_url:
                    print(f"Live stream found: {live_url}", flush=True)
                    values = vars(args).copy()
                    values["url"] = live_url
                    values["watch_channel"] = None
                    values["watch_timeout"] = 0
                    return run(argparse.Namespace(**values))
            elif result.stderr.strip():
                print(f"watch warning: {result.stderr.strip().splitlines()[-1]}", file=sys.stderr, flush=True)
        except (OSError, subprocess.SubprocessError) as exc:
            print(f"watch warning: {exc}", file=sys.stderr, flush=True)
        remaining = args.poll_seconds
        while remaining > 0:
            if deadline is not None:
                remaining = min(remaining, max(0, int(deadline - time.monotonic())))
            if remaining <= 0:
                break
            time.sleep(min(1, remaining))
            remaining -= 1
    print("watch timeout reached without a live stream", file=sys.stderr)
    return 1


def _wait_until(target: datetime) -> bool:
    print(f"Next scheduled start: {target.isoformat(sep=' ', timespec='seconds')}", flush=True)
    try:
        while True:
            remaining = (target - datetime.now()).total_seconds()
            if remaining <= 0:
                return True
            time.sleep(min(1, remaining))
    except KeyboardInterrupt:
        print("Schedule interrupted.", file=sys.stderr, flush=True)
        return False


def _run_cron(args: argparse.Namespace) -> int:
    if not args.url:
        print("error: --cron requires a URL", file=sys.stderr)
        return 2
    if args.queue_file or args.watch_channel or args.start_at:
        print("error: --cron cannot be combined with --queue-file, --watch-channel, or --start-at", file=sys.stderr)
        return 2
    if args.cron_count < 0:
        print("error: --cron-count cannot be negative", file=sys.stderr)
        return 2
    try:
        next_run = next_cron_datetime(args.cron)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    occurrence = 0
    while args.cron_count == 0 or occurrence < args.cron_count:
        if not _wait_until(next_run):
            return 130
        values = vars(args).copy()
        values["cron"] = None
        values["cron_count"] = 0
        result = run(argparse.Namespace(**values))
        if result:
            return result
        occurrence += 1
        try:
            next_run = next_cron_datetime(args.cron, next_run)
        except ValueError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
    print(f"Cron schedule complete: {occurrence} occurrence(s).", flush=True)
    return 0


def run(args: argparse.Namespace) -> int:
    if args.cron:
        return _run_cron(args)
    if args.watch_channel:
        if args.url or args.queue_file:
            print("error: --watch-channel cannot be combined with a URL or --queue-file", file=sys.stderr)
            return 2
        return _run_watch(args)
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
