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
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


SESSION_SCHEMA_VERSION = 1
MANIFEST_SCHEMA_VERSION = 1
SESSION_STATE_FILENAME = ".yt_livestream_session.json"
MANIFEST_FILENAME = ".yt_livestream_manifest.json"
OVERLAP_SECONDS = 2


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
    omits that ffmpeg-specific flag and asks yt-dlp to keep the stream's
    fragments, allowing callers to use a provider-native segment workflow.
    """

    command = [*ytdlp_cmd, "--newline", "--no-part", "--retries", "10", "--fragment-retries", "10"]
    if use_native_segmenter:
        command.extend(["--keep-fragments", "--hls-use-mpegts"])
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
