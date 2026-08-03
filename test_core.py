import json

from yt_livestream_core import (
    MANIFEST_FILENAME,
    SESSION_STATE_FILENAME,
    ManifestStore,
    RecordingSession,
    atomic_write_json,
    build_capture_command,
    build_embed_chapters_command,
    build_live_chat_command,
    build_trim_command,
    chapter_events_for_segment,
    format_ffmetadata_chapters,
    load_session,
    load_queue_items,
    parse_superchat_events,
    parse_progress_line,
    quality_fallback_ladder,
    safe_filename,
)


def test_safe_filename_handles_reserved_characters_and_empty_titles():
    assert safe_filename('A:/ stream <live>?') == "A_ stream _live"
    assert safe_filename("...   ") == "livestream"


def test_quality_fallback_ladder_is_ordered():
    assert quality_fallback_ladder("1080p") == ["1080p", "720p", "480p", "Best"]
    assert quality_fallback_ladder("720p") == ["720p", "480p", "Best"]
    assert quality_fallback_ladder("Audio Only") == ["Audio Only"]


def test_capture_and_trim_commands_keep_overlap_duration_explicit():
    command = build_capture_command(
        ["python", "-m", "yt_dlp"],
        "https://youtu.be/example",
        "segment.tmp.mp4",
        "720p",
        182,
    )
    assert "--downloader" in command
    assert "ffmpeg:-t 182" in command
    assert command[-1] == "https://youtu.be/example"
    assert build_trim_command("ffmpeg", "raw.mp4", "final.mp4", 2)[-3:] == [
        "-avoid_negative_ts",
        "make_zero",
        "final.mp4",
    ]
    native_command = build_capture_command(
        ["yt-dlp"],
        "https://youtu.be/example",
        "native.mp4",
        "Best",
        180,
        use_native_segmenter=True,
    )
    assert native_command[native_command.index("--downloader") + 1] == "native"
    assert "--downloader-args" not in native_command


def test_recording_session_round_trips_atomically(tmp_path):
    session = RecordingSession(
        url="https://www.youtube.com/watch?v=abc",
        output_dir=str(tmp_path),
        next_segment=4,
        segment_minutes=5,
        quality="480p",
        max_retries=2,
    )
    session.save()

    assert (tmp_path / SESSION_STATE_FILENAME).exists()
    restored = load_session(tmp_path)
    assert restored is not None
    assert restored.next_segment == 4
    assert restored.quality == "480p"
    restored.advance(4)
    assert load_session(tmp_path).next_segment == 5


def test_manifest_records_sha256_and_is_replaced_without_duplicate_paths(tmp_path):
    segment = tmp_path / "segment001.mp4"
    segment.write_bytes(b"segment-data")
    manifest = ManifestStore.open(tmp_path, "session-1")

    first = manifest.record_segment(segment, 1, quality="Best", duration_seconds=60)
    segment.write_bytes(b"updated-segment-data")
    second = manifest.record_segment(segment, 1, quality="Best", duration_seconds=60)

    assert first["sha256"] != second["sha256"]
    payload = json.loads((tmp_path / MANIFEST_FILENAME).read_text(encoding="utf-8"))
    assert len(payload["segments"]) == 1
    assert payload["segments"][0]["size_bytes"] == len(b"updated-segment-data")


def test_progress_parser_clamps_invalid_percentages():
    assert parse_progress_line("[download] 33.5% of 10MiB") == 33.5
    assert parse_progress_line("no progress") is None
    assert parse_progress_line("[download] 180%") == 100.0


def test_atomic_json_write_creates_parent_and_valid_json(tmp_path):
    target = tmp_path / "nested" / "state.json"
    atomic_write_json(target, {"ok": True})
    assert json.loads(target.read_text(encoding="utf-8")) == {"ok": True}


def test_queue_loader_accepts_array_and_normalizes_output_alias(tmp_path):
    queue_path = tmp_path / "queue.json"
    queue_path.write_text(
        json.dumps({"items": [{"url": " https://youtu.be/one ", "output_dir": "captures"}]}),
        encoding="utf-8",
    )
    assert load_queue_items(queue_path) == [
        {"url": "https://youtu.be/one", "output_dir": "captures", "output": "captures"}
    ]


def test_live_chat_command_and_superchat_chapter_parser():
    command = build_live_chat_command(["yt-dlp"], "https://youtu.be/example", "stream.%(ext)s")
    assert "--skip-download" in command
    assert command[command.index("--sub-langs") + 1] == "live_chat"
    assert command[-1] == "https://youtu.be/example"

    records = [
        {
            "videoOffsetTimeMsec": "12500",
            "replayChatItemAction": {
                "actions": [
                    {
                        "addChatItemAction": {
                            "item": {
                                "liveChatPaidMessageRenderer": {
                                    "purchaseAmountText": {"simpleText": "$5.00"},
                                    "authorName": {"simpleText": "Ada"},
                                    "message": {"runs": [{"text": "Great show!"}]},
                                }
                            }
                        }
                    }
                ]
            },
        }
    ]
    events = parse_superchat_events(records)
    assert events == [
        {
            "offset_ms": 12500,
            "title": "Super Chat $5.00 — Ada",
            "message": "Great show!",
            "amount": "$5.00",
            "author": "Ada",
        }
    ]
    segment_events = chapter_events_for_segment(events, 2, 10)
    assert segment_events[0]["start_ms"] == 2500
    segment_events = chapter_events_for_segment(events, 1, 20)
    assert segment_events[0]["start_ms"] == 12500


def test_ffmetadata_chapters_escape_text_and_embed_command(tmp_path):
    metadata = format_ffmetadata_chapters(
        [{"start_ms": 1000, "title": "A=B; C", "message": "hello #1"}],
        30,
    )
    assert "title=A\\=B\\; C" in metadata
    assert "comment=hello \\#1" in metadata
    command = build_embed_chapters_command("ffmpeg", "input.m4a", "chapters.ffmeta", "output.m4a")
    assert command[-1] == "output.m4a"
    assert "-map_metadata" in command
