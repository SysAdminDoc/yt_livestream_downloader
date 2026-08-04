"""Testable, dependency-free building blocks for YT Livestream Downloader.

The desktop application imports this module after its optional dependency
bootstrap.  Keeping persistence and command construction here also gives the
headless CLI a single source of truth for recording semantics.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import tempfile
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence
from urllib.parse import urlparse


SESSION_SCHEMA_VERSION = 1
MANIFEST_SCHEMA_VERSION = 1
SESSION_STATE_FILENAME = ".yt_livestream_session.json"
MANIFEST_FILENAME = ".yt_livestream_manifest.json"
OVERLAP_SECONDS = 2
APP_NAME = "YT Livestream Downloader"
APP_VERSION = "1.1.0"
BACKEND_CHOICES = ("auto", "yt-dlp", "streamlink")


FORMAT_SELECTORS: dict[str, str | None] = {
    "Best": None,
    "1080p": "b[height<=1080]/bv[height<=1080]+ba/b",
    "720p": "b[height<=720]/bv[height<=720]+ba/b",
    "480p": "b[height<=480]/bv[height<=480]+ba/b",
    "Audio Only": "ba/b",
}


def utc_now() -> str:
    """Return a stable, timezone-aware timestamp for persisted metadata."""

    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def safe_filename(name: str, fallback: str = "livestream", max_length: int = 80) -> str:
    """Return a Windows/macOS/Linux-safe filename stem."""

    value = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", str(name or ""))
    value = re.sub(r"[.\s]+$", "", value)
    value = re.sub(r"_+", "_", value).strip("_ ")
    return (value[:max_length].rstrip("_ ") or fallback)


def format_selector(quality: str) -> str | None:
    """Return the yt-dlp format selector for a user-facing quality label."""

    return FORMAT_SELECTORS.get(quality, FORMAT_SELECTORS["Best"])


def extension_for_quality(quality: str) -> str:
    return "m4a" if quality == "Audio Only" else "mp4"


def quality_fallback_ladder(quality: str) -> list[str]:
    """Return progressively safer quality choices for a recording attempt."""

    if quality == "Audio Only":
        return [quality]
    ordered = ["1080p", "720p", "480p", "Best"]
    if quality not in ordered:
        return ["Best"]
    return [quality, *[candidate for candidate in ordered if candidate != quality and ordered.index(candidate) > ordered.index(quality)]]


def is_youtube_url(url: str) -> bool:
    """Return whether a URL belongs to YouTube's normal web domains."""

    host = (urlparse(str(url)).hostname or "").casefold().rstrip(".")
    return host == "youtu.be" or host == "youtube.com" or host.endswith(".youtube.com")


def resolve_capture_backend(url: str, backend: str = "auto") -> str:
    """Resolve the requested backend, routing non-YouTube URLs to Streamlink in auto mode."""

    normalized = str(backend or "auto").strip().casefold()
    aliases = {"yt_dlp": "yt-dlp", "ytdlp": "yt-dlp"}
    normalized = aliases.get(normalized, normalized)
    if normalized not in BACKEND_CHOICES:
        choices = ", ".join(BACKEND_CHOICES)
        raise ValueError(f"backend must be one of: {choices}")
    if normalized == "auto":
        return "yt-dlp" if is_youtube_url(url) else "streamlink"
    return normalized


def streamlink_stream_name(quality: str) -> str:
    """Map the shared quality labels to Streamlink stream names."""

    return {
        "Best": "best",
        "1080p": "1080p",
        "720p": "720p",
        "480p": "480p",
        "Audio Only": "audio_only",
    }.get(quality, "best")


def build_streamlink_command(
    streamlink_cmd: Sequence[str],
    url: str,
    quality: str,
) -> list[str]:
    """Build a Streamlink stdout command for one bounded FFmpeg capture."""

    return [
        *streamlink_cmd,
        "--stdout",
        "--retry-open",
        "3",
        "--retry-streams",
        "3",
        url,
        streamlink_stream_name(quality),
    ]


def build_streamlink_mux_command(
    ffmpeg_path: str,
    output_path: str | os.PathLike[str],
    quality: str,
    duration_seconds: int,
) -> list[str]:
    """Build the FFmpeg side of the Streamlink-to-file capture pipe."""

    command = [
        ffmpeg_path,
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-i",
        "pipe:0",
        "-t",
        str(max(1, int(duration_seconds))),
    ]
    if quality == "Audio Only":
        command.extend(["-vn", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart"])
    else:
        command.extend(
            [
                "-map",
                "0:v:0?",
                "-map",
                "0:a:0?",
                "-c:v",
                "copy",
                "-c:a",
                "aac",
                "-b:a",
                "192k",
                "-movflags",
                "+faststart",
            ]
        )
    command.append(os.fspath(output_path))
    return command


def build_capture_command(
    ytdlp_cmd: Sequence[str],
    url: str,
    output_path: str | os.PathLike[str],
    quality: str,
    duration_seconds: int | None,
    *,
    use_native_segmenter: bool = False,
    live_from_start: bool = False,
    write_subtitles: bool = False,
    subtitle_languages: str = "en.*",
) -> list[str]:
    """Build a deterministic yt-dlp command for one capture writer.

    The default writer uses ffmpeg's time bound.  The native path deliberately
    omits that ffmpeg-specific flag and asks yt-dlp to use its fragment
    downloader, allowing DASH streams to be captured without ffmpeg.  yt-dlp
    currently rejects native HLS livestream downloads; the worker detects that
    failure and falls back to the ffmpeg writer.
    """

    command = [*ytdlp_cmd, "--newline", "--no-part", "--retries", "10", "--fragment-retries", "10"]
    if use_native_segmenter:
        command.extend(["--downloader", "native", "--keep-fragments"])
    else:
        if duration_seconds is not None:
            command.extend(["--downloader", "ffmpeg", "--downloader-args", f"ffmpeg:-t {int(duration_seconds)}"])
    if live_from_start:
        command.append("--live-from-start")
    if write_subtitles:
        command.extend(["--write-auto-subs", "--sub-langs", subtitle_languages])
    if quality == "Audio Only":
        command.extend(["-x", "--audio-format", "m4a", "--audio-quality", "0"])
    selector = format_selector(quality)
    if selector:
        command.extend(["-f", selector])
    command.extend(["-o", os.fspath(output_path), url])
    return command


def build_trim_command(
    ffmpeg_path: str,
    input_path: str | os.PathLike[str],
    output_path: str | os.PathLike[str],
    trim_seconds: int = OVERLAP_SECONDS,
) -> list[str]:
    """Build a stream-copy trim command for the overlap prefix."""

    return [
        ffmpeg_path,
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-ss",
        str(max(0, int(trim_seconds))),
        "-i",
        os.fspath(input_path),
        "-c",
        "copy",
        "-avoid_negative_ts",
        "make_zero",
        os.fspath(output_path),
    ]


def format_concat_file_list(paths: Iterable[str | os.PathLike[str]]) -> str:
    """Format paths for ffmpeg's concat demuxer list file."""

    lines = []
    for path in paths:
        value = os.fspath(path).replace("\\", "/").replace("'", "'\\''")
        lines.append(f"file '{value}'")
    return "\n".join(lines) + ("\n" if lines else "")


def build_concat_command(
    ffmpeg_path: str,
    list_path: str | os.PathLike[str],
    output_path: str | os.PathLike[str],
) -> list[str]:
    return [
        ffmpeg_path,
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        os.fspath(list_path),
        "-c",
        "copy",
        os.fspath(output_path),
    ]


def build_loudnorm_analysis_command(ffmpeg_path: str, input_path: str | os.PathLike[str]) -> list[str]:
    return [
        ffmpeg_path,
        "-hide_banner",
        "-i",
        os.fspath(input_path),
        "-af",
        "loudnorm=I=-16:TP=-1.5:LRA=11:print_format=json",
        "-f",
        "null",
        os.devnull,
    ]


def parse_loudnorm_measurements(output: str) -> dict[str, str] | None:
    """Extract the JSON measurement object emitted by loudnorm's first pass."""

    required = ("input_i", "input_tp", "input_lra", "input_thresh", "target_offset")
    for match in re.finditer(r"\{[^{}]*\}", str(output), re.DOTALL):
        try:
            payload = json.loads(match.group(0))
        except ValueError:
            continue
        if isinstance(payload, Mapping) and all(key in payload for key in required):
            return {key: str(payload[key]) for key in required}
    return None


def build_postprocess_command(
    ffmpeg_path: str,
    input_path: str | os.PathLike[str],
    output_path: str | os.PathLike[str],
    *,
    h265: bool = False,
    loudnorm_measurements: Mapping[str, str] | None = None,
    silence_skip_seconds: float = 0.0,
) -> list[str]:
    """Build the final transcode command after concat and optional loudnorm analysis."""

    command = [
        ffmpeg_path,
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-i",
        os.fspath(input_path),
        "-map",
        "0",
    ]
    filters = []
    if silence_skip_seconds > 0:
        filters.append(
            f"silenceremove=stop_periods=-1:stop_duration={float(silence_skip_seconds):g}:stop_threshold=-45dB"
        )
    if loudnorm_measurements:
        filter_value = (
            "loudnorm=I=-16:TP=-1.5:LRA=11:"
            f"measured_I={loudnorm_measurements['input_i']}:"
            f"measured_TP={loudnorm_measurements['input_tp']}:"
            f"measured_LRA={loudnorm_measurements['input_lra']}:"
            f"measured_thresh={loudnorm_measurements['input_thresh']}:"
            f"offset={loudnorm_measurements['target_offset']}:linear=true:print_format=summary"
        )
        filters.append(filter_value)
    if filters:
        command.extend(["-af", ",".join(filters)])
    command.extend(["-c:v", "libx265" if h265 else "copy"])
    if h265:
        command.extend(["-crf", "23", "-preset", "medium"])
    command.extend(["-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", os.fspath(output_path)])
    return command


def build_thumbnail_command(
    ffmpeg_path: str,
    input_path: str | os.PathLike[str],
    interval_seconds: int,
    output_pattern: str | os.PathLike[str],
) -> list[str]:
    return [
        ffmpeg_path,
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-i",
        os.fspath(input_path),
        "-vf",
        f"fps=1/{max(1, int(interval_seconds))}",
        "-q:v",
        "2",
        os.fspath(output_pattern),
    ]


def build_mpv_command(mpv_path: str, url: str, window_id: int) -> list[str]:
    """Build an input-free embedded mpv command for the optional mini-player."""

    return [
        mpv_path,
        "--no-terminal",
        "--force-window=yes",
        "--no-osc",
        "--no-input-default-bindings",
        "--keep-open=no",
        f"--wid={int(window_id)}",
        "--",
        url,
    ]


def build_rclone_copy_command(
    rclone_path: str,
    filepath: str | os.PathLike[str],
    remote: str,
) -> list[str]:
    """Build a single-file rclone upload that does not traverse the remote."""

    target = f"{remote.rstrip('/')}/{Path(filepath).name}"
    return [rclone_path, "copyto", os.fspath(filepath), target, "--no-traverse"]


def build_live_chat_command(
    ytdlp_cmd: Sequence[str],
    url: str,
    output_template: str | os.PathLike[str],
) -> list[str]:
    """Build a sidecar capture command for YouTube's live-chat subtitle stream."""

    return [
        *ytdlp_cmd,
        "--skip-download",
        "--write-subs",
        "--sub-langs",
        "live_chat",
        "--sub-format",
        "json",
        "--no-part",
        "--force-overwrites",
        "-o",
        os.fspath(output_template),
        url,
    ]


def build_channel_watch_command(ytdlp_cmd: Sequence[str], channel_url: str) -> list[str]:
    """Build a lightweight poll command for a channel's public live tab."""

    target = channel_url.rstrip("/")
    if not target.endswith("/live"):
        target = f"{target}/live"
    return [
        *ytdlp_cmd,
        "--flat-playlist",
        "--playlist-end",
        "1",
        "--dump-single-json",
        "--skip-download",
        target,
    ]


def parse_channel_live_result(source: Any) -> str | None:
    """Return a live video's watch URL from a yt-dlp channel poll payload."""

    payload = source
    if isinstance(source, (str, os.PathLike)):
        try:
            with open(source, encoding="utf-8") as handle:
                payload = json.load(handle)
        except (OSError, ValueError):
            return None
    if isinstance(payload, Mapping):
        entries = payload.get("entries")
        candidates = entries if isinstance(entries, list) else [payload]
    elif isinstance(payload, list):
        candidates = payload
    else:
        return None
    for entry in candidates:
        if not isinstance(entry, Mapping):
            continue
        status = str(entry.get("live_status") or entry.get("liveStatus") or "").lower()
        if not entry.get("is_live") and status not in {"is_live", "live"}:
            continue
        url = entry.get("webpage_url") or entry.get("url")
        video_id = entry.get("id") or entry.get("videoId")
        if isinstance(url, str) and url.startswith(("http://", "https://")):
            return url
        if isinstance(video_id, str) and video_id:
            return f"https://www.youtube.com/watch?v={video_id}"
    return None


def _cron_field(spec: str, minimum: int, maximum: int, name: str) -> tuple[set[int], bool]:
    values: set[int] = set()
    wildcard = spec == "*"
    for part in spec.split(","):
        if not part:
            raise ValueError(f"cron {name} field is empty")
        pieces = part.split("/")
        if len(pieces) > 2:
            raise ValueError(f"cron {name} field has too many step separators")
        base = pieces[0]
        try:
            step = int(pieces[1]) if len(pieces) == 2 else 1
        except ValueError as exc:
            raise ValueError(f"cron {name} step is not an integer") from exc
        if step <= 0:
            raise ValueError(f"cron {name} step must be positive")
        if base == "*":
            start, end = minimum, maximum
        elif "-" in base:
            bounds = base.split("-")
            if len(bounds) != 2:
                raise ValueError(f"cron {name} range is invalid")
            try:
                start, end = int(bounds[0]), int(bounds[1])
            except ValueError as exc:
                raise ValueError(f"cron {name} range is not numeric") from exc
        else:
            try:
                start = end = int(base)
            except ValueError as exc:
                raise ValueError(f"cron {name} value is not numeric") from exc
        if start < minimum or end > maximum or start > end:
            raise ValueError(f"cron {name} must be between {minimum} and {maximum}")
        values.update(range(start, end + 1, step))
    if not values:
        raise ValueError(f"cron {name} field has no values")
    return values, wildcard


def parse_cron_expression(expression: str) -> tuple[tuple[set[int], bool], ...]:
    """Parse standard five-field minute/hour/day/month/weekday cron syntax."""

    fields = str(expression).split()
    if len(fields) != 5:
        raise ValueError("cron expression must contain five fields: minute hour day-of-month month weekday")
    minute = _cron_field(fields[0], 0, 59, "minute")
    hour = _cron_field(fields[1], 0, 23, "hour")
    day = _cron_field(fields[2], 1, 31, "day-of-month")
    month = _cron_field(fields[3], 1, 12, "month")
    weekday_values, weekday_wildcard = _cron_field(fields[4], 0, 7, "weekday")
    weekday_values = {0 if value == 7 else value for value in weekday_values}
    return minute, hour, day, month, (weekday_values, weekday_wildcard)


def next_cron_datetime(expression: str, now: datetime | None = None) -> datetime:
    """Return the next local naive datetime matching a five-field cron expression."""

    minute, hour, day, month, weekday = parse_cron_expression(expression)
    now = now or datetime.now()
    candidate = now.replace(second=0, microsecond=0) + timedelta(minutes=1)
    search_limit = 366 * 24 * 60 + 1
    day_values, day_wildcard = day
    weekday_values, weekday_wildcard = weekday
    for _ in range(search_limit):
        if candidate.month not in month[0] or candidate.hour not in hour[0] or candidate.minute not in minute[0]:
            candidate += timedelta(minutes=1)
            continue
        day_match = candidate.day in day_values
        weekday_match = ((candidate.weekday() + 1) % 7) in weekday_values
        if not day_wildcard and not weekday_wildcard:
            calendar_match = day_match or weekday_match
        else:
            calendar_match = day_match and weekday_match
        if calendar_match:
            return candidate
        candidate += timedelta(minutes=1)
    raise ValueError("cron expression has no occurrence within the next year")


def build_notification_payload(event: str, message: str, fields: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Build a Discord-compatible payload that also remains useful to generic webhooks."""

    embed_fields = [
        {"name": str(key), "value": str(value), "inline": True}
        for key, value in (fields or {}).items()
        if value is not None and str(value)
    ]
    return {
        "content": message,
        "embeds": [
            {
                "title": str(event).replace("_", " ").title(),
                "description": message,
                "fields": embed_fields,
                "timestamp": utc_now(),
            }
        ],
    }


def _text_value(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, Mapping):
        if isinstance(value.get("simpleText"), str):
            return value["simpleText"]
        if isinstance(value.get("text"), str):
            return value["text"]
        runs = value.get("runs")
        if isinstance(runs, list):
            return "".join(_text_value(run) for run in runs).strip()
    if isinstance(value, list):
        return "".join(_text_value(item) for item in value).strip()
    return ""


def _walk_mappings(value: Any) -> Iterable[Mapping[str, Any]]:
    if isinstance(value, Mapping):
        yield value
        for child in value.values():
            yield from _walk_mappings(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_mappings(child)


def _first_offset_ms(value: Any) -> int | None:
    for mapping in _walk_mappings(value):
        for key in ("videoOffsetTimeMsec", "offsetMs", "videoOffsetMs"):
            raw = mapping.get(key)
            if raw is not None:
                try:
                    return max(0, int(float(raw)))
                except (TypeError, ValueError):
                    pass
    return None


def _json_records(source: Any) -> Iterable[Mapping[str, Any]]:
    if isinstance(source, (str, os.PathLike)):
        with open(source, encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if line:
                    try:
                        value = json.loads(line)
                    except ValueError:
                        continue
                    if isinstance(value, Mapping):
                        yield value
        return
    if isinstance(source, Mapping):
        records = source.get("events")
        if isinstance(records, list):
            yield from (item for item in records if isinstance(item, Mapping))
        else:
            yield source
        return
    if isinstance(source, list):
        yield from (item for item in source if isinstance(item, Mapping))


def parse_superchat_events(source: Any) -> list[dict[str, Any]]:
    """Extract paid live-chat messages as relative millisecond chapter events."""

    renderer_keys = {
        "liveChatPaidMessageRenderer",
        "liveChatPaidStickerRenderer",
        "liveChatTickerPaidMessageItemRenderer",
    }
    events: list[dict[str, Any]] = []
    seen: set[tuple[int, str, str]] = set()
    for record in _json_records(source):
        offset_ms = _first_offset_ms(record)
        if offset_ms is None:
            continue
        for mapping in _walk_mappings(record):
            for key in renderer_keys.intersection(mapping):
                renderer = mapping.get(key)
                if not isinstance(renderer, Mapping):
                    continue
                amount = _text_value(
                    renderer.get("purchaseAmountText")
                    or renderer.get("amount")
                    or renderer.get("purchaseAmount")
                )
                author = _text_value(renderer.get("authorName") or renderer.get("author"))
                message = _text_value(renderer.get("message") or renderer.get("headerSubtext"))
                title = "Super Chat"
                if amount:
                    title = f"Super Chat {amount}"
                if author:
                    title = f"{title} — {author}"
                identity = (offset_ms, title, message)
                if identity in seen:
                    continue
                seen.add(identity)
                events.append(
                    {
                        "offset_ms": offset_ms,
                        "title": title,
                        "message": message,
                        "amount": amount,
                        "author": author,
                    }
                )
    return sorted(events, key=lambda event: (event["offset_ms"], event["title"]))


def parse_milestone_events(source: Any, keywords: Iterable[str]) -> list[dict[str, Any]]:
    """Extract keyword-matching live-chat messages as chapter events."""

    wanted = [str(keyword).strip() for keyword in keywords if str(keyword).strip()]
    normalized = [(keyword, keyword.casefold()) for keyword in wanted]
    if not normalized:
        return []
    renderer_keys = {
        "liveChatTextMessageRenderer",
        "liveChatPaidMessageRenderer",
        "liveChatTickerPaidMessageItemRenderer",
        "liveChatMembershipItemRenderer",
    }
    events: list[dict[str, Any]] = []
    seen: set[tuple[int, str, str]] = set()
    for record in _json_records(source):
        offset_ms = _first_offset_ms(record)
        if offset_ms is None:
            continue
        for mapping in _walk_mappings(record):
            for key in renderer_keys.intersection(mapping):
                renderer = mapping.get(key)
                if not isinstance(renderer, Mapping):
                    continue
                message = _text_value(renderer.get("message") or renderer.get("headerSubtext") or renderer.get("primaryText"))
                haystack = message.casefold()
                for keyword, folded in normalized:
                    if folded not in haystack:
                        continue
                    identity = (offset_ms, keyword.casefold(), message)
                    if identity in seen:
                        continue
                    seen.add(identity)
                    events.append(
                        {
                            "offset_ms": offset_ms,
                            "title": f"Milestone — {keyword}",
                            "message": message,
                            "keyword": keyword,
                        }
                    )
                    break
    return sorted(events, key=lambda event: (event["offset_ms"], event["title"]))


def video_chapter_events(info: Mapping[str, Any] | None) -> list[dict[str, Any]]:
    """Normalize yt-dlp's returned chapter list to the shared event format."""

    if not isinstance(info, Mapping) or not isinstance(info.get("chapters"), list):
        return []
    events = []
    for chapter in info["chapters"]:
        if not isinstance(chapter, Mapping):
            continue
        try:
            start_ms = max(0, int(float(chapter.get("start_time", 0)) * 1000))
        except (TypeError, ValueError):
            continue
        events.append(
            {
                "offset_ms": start_ms,
                "title": str(chapter.get("title") or "Chapter"),
                "message": "",
            }
        )
    return sorted(events, key=lambda event: event["offset_ms"])


def chapter_events_for_segment(
    events: Iterable[Mapping[str, Any]],
    segment_number: int,
    segment_seconds: int,
    *,
    first_segment_number: int = 1,
) -> list[dict[str, Any]]:
    """Translate stream-relative chat events into one segment's timeline."""

    segment_start_ms = max(0, segment_number - first_segment_number) * int(segment_seconds) * 1000
    segment_end_ms = segment_start_ms + int(segment_seconds) * 1000
    selected = []
    for event in events:
        try:
            offset_ms = int(event["offset_ms"])
        except (KeyError, TypeError, ValueError):
            continue
        if segment_start_ms <= offset_ms < segment_end_ms:
            selected.append(
                {
                    "start_ms": offset_ms - segment_start_ms,
                    "title": str(event.get("title") or "Super Chat"),
                    "message": str(event.get("message") or ""),
                }
            )
    return selected


def _escape_ffmetadata(value: str) -> str:
    return str(value).replace("\\", "\\\\").replace("=", "\\=").replace(";", "\\;").replace("#", "\\#").replace("\n", " ")


def format_ffmetadata_chapters(events: Iterable[Mapping[str, Any]], duration_seconds: int) -> str:
    """Format chapter events in ffmetadata's millisecond timebase."""

    normalized = sorted(
        (
            max(0, int(event.get("start_ms", 0))),
            _escape_ffmetadata(str(event.get("title") or "Super Chat")),
            _escape_ffmetadata(str(event.get("message") or "")),
        )
        for event in events
    )
    lines = [";FFMETADATA1"]
    for index, (start_ms, title, message) in enumerate(normalized):
        end_ms = normalized[index + 1][0] if index + 1 < len(normalized) else max(start_ms + 1, int(duration_seconds * 1000))
        end_ms = max(start_ms + 1, min(end_ms, int(duration_seconds * 1000)))
        lines.extend(
            [
                "[CHAPTER]",
                "TIMEBASE=1/1000",
                f"START={start_ms}",
                f"END={end_ms}",
                f"title={title}",
            ]
        )
        if message:
            lines.append(f"comment={message}")
    return "\n".join(lines) + "\n"


def build_embed_chapters_command(
    ffmpeg_path: str,
    media_path: str | os.PathLike[str],
    metadata_path: str | os.PathLike[str],
    output_path: str | os.PathLike[str],
) -> list[str]:
    return [
        ffmpeg_path,
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-i",
        os.fspath(media_path),
        "-i",
        os.fspath(metadata_path),
        "-map",
        "0:a:0",
        "-map_metadata",
        "1",
        "-c:a",
        "copy",
        os.fspath(output_path),
    ]


def atomic_write_json(path: str | os.PathLike[str], payload: Mapping[str, Any]) -> None:
    """Atomically replace a JSON file, including when interrupted mid-write."""

    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".tmp", dir=target.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_name, target)
    finally:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass


def read_json(path: str | os.PathLike[str]) -> dict[str, Any] | None:
    try:
        with open(path, encoding="utf-8") as handle:
            value = json.load(handle)
        return value if isinstance(value, dict) else None
    except (OSError, ValueError, TypeError):
        return None


def load_queue_items(path: str | os.PathLike[str]) -> list[dict[str, Any]]:
    """Load a validated JSON queue containing one URL per item.

    The file may be either a JSON array or an object with an ``items`` array.
    Each item can override CLI defaults with ``output``, ``start_at``,
    ``quality``, ``segment_minutes``, ``retries``, and the capture booleans.
    """

    with open(path, encoding="utf-8") as handle:
        payload = json.load(handle)
    items = payload.get("items") if isinstance(payload, Mapping) else payload
    if not isinstance(items, list) or not items:
        raise ValueError("queue file must contain a non-empty JSON array or an object with an items array")
    normalized: list[dict[str, Any]] = []
    for index, item in enumerate(items, start=1):
        if not isinstance(item, Mapping):
            raise ValueError(f"queue item {index} must be a JSON object")
        url = str(item.get("url", "")).strip()
        if not url:
            raise ValueError(f"queue item {index} is missing url")
        value = dict(item)
        value["url"] = url
        if "output_dir" in value and "output" not in value:
            value["output"] = value["output_dir"]
        normalized.append(value)
    return normalized


@dataclass
class RecordingSession:
    """Crash-resumable recording state stored inside the output directory."""

    url: str
    output_dir: str
    next_segment: int = 1
    segment_minutes: int = 30
    quality: str = "Best"
    max_retries: int = 3
    filename_prefix: str = ""
    session_id: str = ""
    stream_title: str = ""
    started_at: str = field(default_factory=utc_now)
    updated_at: str = field(default_factory=utc_now)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["schema_version"] = SESSION_SCHEMA_VERSION
        return payload

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "RecordingSession | None":
        if payload.get("schema_version", SESSION_SCHEMA_VERSION) != SESSION_SCHEMA_VERSION:
            return None
        try:
            return cls(
                url=str(payload["url"]),
                output_dir=str(payload["output_dir"]),
                next_segment=max(1, int(payload.get("next_segment", 1))),
                segment_minutes=max(1, int(payload.get("segment_minutes", 30))),
                quality=str(payload.get("quality", "Best")),
                max_retries=max(0, int(payload.get("max_retries", 3))),
                filename_prefix=str(payload.get("filename_prefix", "")),
                session_id=str(payload.get("session_id", "")),
                stream_title=str(payload.get("stream_title", "")),
                started_at=str(payload.get("started_at", utc_now())),
                updated_at=str(payload.get("updated_at", utc_now())),
            )
        except (KeyError, TypeError, ValueError):
            return None

    @property
    def path(self) -> Path:
        return Path(self.output_dir) / SESSION_STATE_FILENAME

    def save(self) -> None:
        self.updated_at = utc_now()
        atomic_write_json(self.path, self.to_dict())

    def advance(self, completed_segment: int) -> None:
        self.next_segment = max(self.next_segment, completed_segment + 1)
        self.save()


def load_session(output_dir: str | os.PathLike[str]) -> RecordingSession | None:
    payload = read_json(Path(output_dir) / SESSION_STATE_FILENAME)
    return RecordingSession.from_dict(payload) if payload else None


def clear_session(output_dir: str | os.PathLike[str]) -> None:
    try:
        (Path(output_dir) / SESSION_STATE_FILENAME).unlink()
    except FileNotFoundError:
        pass


@dataclass
class ManifestStore:
    """Atomic per-segment checksum manifest."""

    path: Path
    session_id: str
    entries: list[dict[str, Any]] = field(default_factory=list)

    @classmethod
    def open(cls, output_dir: str | os.PathLike[str], session_id: str = "") -> "ManifestStore":
        path = Path(output_dir) / MANIFEST_FILENAME
        existing = read_json(path) or {}
        entries = existing.get("segments", [])
        if not isinstance(entries, list):
            entries = []
        return cls(path=path, session_id=session_id or str(existing.get("session_id", "")), entries=entries)

    def save(self) -> None:
        atomic_write_json(
            self.path,
            {
                "schema_version": MANIFEST_SCHEMA_VERSION,
                "session_id": self.session_id,
                "updated_at": utc_now(),
                "segments": self.entries,
            },
        )

    def record_segment(
        self,
        filepath: str | os.PathLike[str],
        segment_number: int,
        *,
        quality: str,
        duration_seconds: int,
        partial: bool = False,
    ) -> dict[str, Any]:
        path = Path(filepath)
        entry = {
            "segment": int(segment_number),
            "filename": path.name,
            "path": str(path),
            "size_bytes": path.stat().st_size,
            "sha256": sha256_file(path),
            "quality": quality,
            "duration_seconds": int(duration_seconds),
            "partial": bool(partial),
            "recorded_at": utc_now(),
        }
        self.entries = [item for item in self.entries if item.get("path") != str(path)]
        self.entries.append(entry)
        self.entries.sort(key=lambda item: int(item.get("segment", 0)))
        self.save()
        return entry


def sha256_file(path: str | os.PathLike[str], chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        while chunk := handle.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


@dataclass(frozen=True)
class DiskSpaceStatus:
    free_bytes: int
    total_bytes: int
    warn_bytes: int
    pause_bytes: int

    @property
    def level(self) -> str:
        if self.free_bytes <= self.pause_bytes:
            return "pause"
        if self.free_bytes <= self.warn_bytes:
            return "warn"
        return "ok"


def check_disk_space(path: str | os.PathLike[str], warn_gb: float = 5.0, pause_gb: float = 1.0) -> DiskSpaceStatus:
    target = Path(path)
    probe = target if target.exists() else target.parent
    usage = shutil.disk_usage(probe)
    return DiskSpaceStatus(
        free_bytes=usage.free,
        total_bytes=usage.total,
        warn_bytes=max(0, int(warn_gb * 1024**3)),
        pause_bytes=max(0, int(pause_gb * 1024**3)),
    )


def parse_progress_line(line: str) -> float | None:
    """Extract a 0..100 percentage from a yt-dlp progress line."""

    match = re.search(r"(?<!\d)(\d{1,3}(?:\.\d+)?)%", line)
    if not match:
        return None
    value = float(match.group(1))
    return max(0.0, min(100.0, value))


def manifest_entries_for_paths(manifest: ManifestStore, paths: Iterable[str | os.PathLike[str]]) -> list[dict[str, Any]]:
    wanted = {str(Path(path)) for path in paths}
    return [entry for entry in manifest.entries if entry.get("path") in wanted]
