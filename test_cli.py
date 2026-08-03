from datetime import datetime

import pytest

from yt_livestream_cli import _parse_start_at, build_parser


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
            "--start-at",
            "2026-08-03T20:00:00",
        ]
    )
    assert args.quality == "Audio Only"
    assert args.resume is True
    assert args.superchat_chapters is True
    assert args.start_at == "2026-08-03T20:00:00"


def test_cli_start_at_accepts_iso_and_zulu_values():
    assert _parse_start_at("2026-08-03T20:00:00") == datetime(2026, 8, 3, 20, 0)
    assert _parse_start_at("2026-08-03T20:00:00Z").year == 2026


def test_cli_start_at_rejects_invalid_values():
    with pytest.raises(ValueError, match="invalid --start-at"):
        _parse_start_at("tomorrow")
