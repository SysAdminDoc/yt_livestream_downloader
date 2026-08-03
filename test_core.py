import json
from datetime import datetime

from yt_livestream_core import (
    MANIFEST_FILENAME,
    SESSION_STATE_FILENAME,
    ManifestStore,
    RecordingSession,
    atomic_write_json,
    build_capture_command,
    build_channel_watch_command,
    build_concat_command,
    build_loudnorm_analysis_command,
    build_mpv_command,
    build_postprocess_command,
    build_embed_chapters_command,
    build_live_chat_command,
    build_notification_payload,
    build_trim_command,
    chapter_events_for_segment,
    format_ffmetadata_chapters,
    format_concat_file_list,
    load_session,
    load_queue_items,
    parse_superchat_events,
    parse_progress_line,
    parse_channel_live_result,
    parse_milestone_events,
    parse_loudnorm_measurements,
    next_cron_datetime,
    parse_cron_expression,
    quality_fallback_ladder,
    safe_filename,
    video_chapter_events,
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
    subtitle_command = build_capture_command(
        ["yt-dlp"], "https://youtu.be/example", "segment.mp4", "Best", 30, write_subtitles=True
    )
    assert "--write-auto-subs" in subtitle_command
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


def test_channel_watch_command_and_live_result_parser():
    command = build_channel_watch_command(["yt-dlp"], "https://www.youtube.com/@creator")
    assert command[-1] == "https://www.youtube.com/@creator/live"
    assert "--flat-playlist" in command
    assert parse_channel_live_result({"entries": [{"id": "abc", "live_status": "is_live"}]}) == (
        "https://www.youtube.com/watch?v=abc"
    )
    assert parse_channel_live_result({"entries": [{"id": "abc", "live_status": "was_live"}]}) is None


def test_cron_parser_finds_next_weekday_occurrence_and_rejects_bad_syntax():
    now = datetime(2026, 8, 3, 19, 59, 30)
    assert next_cron_datetime("*/15 20 * * 1-5", now) == datetime(2026, 8, 3, 20, 0)
    assert len(parse_cron_expression("0 8 * * 1-5")) == 5
    try:
        parse_cron_expression("0 8 * *")
    except ValueError as exc:
        assert "five fields" in str(exc)
    else:
        raise AssertionError("invalid cron expression was accepted")


def test_notification_payload_is_discord_compatible_and_structured():
    payload = build_notification_payload("segment_complete", "Segment saved", {"segment": 2, "path": "capture.m4a"})
    assert payload["content"] == "Segment saved"
    assert payload["embeds"][0]["title"] == "Segment Complete"
    assert {field["name"] for field in payload["embeds"][0]["fields"]} == {"segment", "path"}


def test_postprocess_commands_cover_concat_h265_and_two_pass_loudnorm():
    assert format_concat_file_list([r"C:\captures\one.mp4", "two.mp4"]) == "file 'C:/captures/one.mp4'\nfile 'two.mp4'\n"
    concat = build_concat_command("ffmpeg", "concat.txt", "joined.mp4")
    assert concat[concat.index("-f") + 1] == "concat"
    analysis = build_loudnorm_analysis_command("ffmpeg", "joined.mp4")
    assert "loudnorm=I=-16:TP=-1.5:LRA=11:print_format=json" in analysis
    measurements = parse_loudnorm_measurements(
        'noise\n{"input_i":"-20.0","input_tp":"-1.0","input_lra":"5.0","input_thresh":"-30.0","target_offset":"0.1"}'
    )
    assert measurements["input_i"] == "-20.0"
    final = build_postprocess_command("ffmpeg", "joined.mp4", "final.mp4", h265=True, loudnorm_measurements=measurements)
    assert "libx265" in final
    assert any(argument.startswith("loudnorm=I=-16") for argument in final)


def test_mpv_command_is_embedded_and_disables_default_input_bindings():
    command = build_mpv_command("mpv", "https://youtu.be/example", 12345)
    assert "--wid=12345" in command
    assert "--no-input-default-bindings" in command
    assert command[-2:] == ["--", "https://youtu.be/example"]


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


def test_milestone_and_video_chapter_events_share_the_same_timeline():
    records = [
        {
            "videoOffsetTimeMsec": 5000,
            "addChatItemAction": {
                "item": {
                    "liveChatTextMessageRenderer": {
                        "message": {"simpleText": "Milestone reached!"}
                    }
                }
            },
        }
    ]
    assert parse_milestone_events(records, ["milestone"])[0]["title"] == "Milestone — milestone"
    assert video_chapter_events({"chapters": [{"start_time": 12.5, "title": "Opening"}]}) == [
        {"offset_ms": 12500, "title": "Opening", "message": ""}
    ]


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
