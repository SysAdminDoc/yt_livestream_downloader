from datetime import datetime

import pytest

from yt_livestream_cli import _parse_start_at, _queue_namespace, build_parser


def test_cli_parser_exposes_capture_controls():
    args = build_parser().parse_args(
        [
            "https://youtu.be/example",
            "--quality",
            "Audio Only",
            "--resume",
            "--native-fragments",
            "--live-from-start",
            "--write-auto-sub",
            "--superchat-chapters",
            "--capture-live-chat",
            "--silence-skip",
            "3",
            "--thumbnail-seconds",
            "30",
            "--start-at",
            "2026-08-03T20:00:00",
        ]
    )
    assert args.quality == "Audio Only"
    assert args.resume is True
    assert args.superchat_chapters is True
    assert args.capture_live_chat is True
    assert args.silence_skip == 3
    assert args.thumbnail_seconds == 30
    assert args.start_at == "2026-08-03T20:00:00"


def test_cli_start_at_accepts_iso_and_zulu_values():
    assert _parse_start_at("2026-08-03T20:00:00") == datetime(2026, 8, 3, 20, 0)
    assert _parse_start_at("2026-08-03T20:00:00Z").year == 2026


def test_cli_start_at_rejects_invalid_values():
    with pytest.raises(ValueError, match="invalid --start-at"):
        _parse_start_at("tomorrow")


def test_queue_item_overrides_are_applied_to_a_base_namespace():
    base = build_parser().parse_args(["--queue-file", "queue.json"])
    queued = _queue_namespace(
        base,
        {"url": "https://youtu.be/queued", "quality": "Audio Only", "start_at": "2026-08-03T20:00:00"},
    )
    assert queued.url == "https://youtu.be/queued"
    assert queued.quality == "Audio Only"
    assert queued.start_at == "2026-08-03T20:00:00"


def test_watch_parser_accepts_polling_controls():
    args = build_parser().parse_args(["--watch-channel", "https://www.youtube.com/@creator", "--poll-seconds", "30"])
    assert args.watch_channel.endswith("@creator")
    assert args.poll_seconds == 30


def test_cron_parser_accepts_finite_schedule():
    args = build_parser().parse_args(["https://youtu.be/example", "--cron", "0 20 * * 2", "--cron-count", "2"])
    assert args.cron == "0 20 * * 2"
    assert args.cron_count == 2
