"""Dependency-free ffmpeg post-processing pipeline shared by GUI and CLI."""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Callable, Iterable

from yt_livestream_core import (
    build_concat_command,
    build_loudnorm_analysis_command,
    build_postprocess_command,
    format_concat_file_list,
    parse_loudnorm_measurements,
    safe_filename,
)


class PostProcessError(RuntimeError):
    """Raised when an optional output post-process cannot complete."""


def run_postprocess(
    paths: Iterable[str | os.PathLike[str]],
    output_dir: str | os.PathLike[str],
    quality: str,
    prefix: str = "",
    *,
    concat: bool = False,
    h265: bool = False,
    loudnorm: bool = False,
    log: Callable[[str], None] | None = None,
) -> Path | None:
    """Concat and optionally transcode finalized segments, returning the output path."""

    if not (concat or h265 or loudnorm):
        return None
    ffmpeg_path = shutil.which("ffmpeg")
    if not ffmpeg_path:
        raise PostProcessError("ffmpeg is unavailable")
    output_root = Path(output_dir)
    segment_paths = [Path(path) for path in paths if Path(path).is_file()]
    if not segment_paths:
        raise PostProcessError("no completed segment files are available")
    output_root.mkdir(parents=True, exist_ok=True)
    title = safe_filename(prefix or segment_paths[0].stem.split("_seg", 1)[0] or "livestream")
    extension = ".m4a" if quality == "Audio Only" else ".mp4"
    final_path = output_root / f"{title}_concat{extension}"
    requires_processing = h265 or loudnorm
    source_path = output_root / f".{title}_concat.source{extension}" if requires_processing else final_path
    list_path: Path | None = None

    def emit(message: str) -> None:
        if log:
            log(message)

    def run_ffmpeg(command: list[str], label: str) -> None:
        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=3600,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise PostProcessError(f"{label} failed: {exc}") from exc
        if result.returncode != 0:
            detail = result.stderr.strip().splitlines()[-1] if result.stderr.strip() else f"exit code {result.returncode}"
            raise PostProcessError(f"{label} failed: {detail}")
        emit(f"{label} complete")

    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            suffix=".concat.txt",
            prefix=".yt_livestream_",
            dir=output_root,
            delete=False,
        ) as handle:
            list_path = Path(handle.name)
            handle.write(format_concat_file_list(segment_paths))
        run_ffmpeg(build_concat_command(ffmpeg_path, list_path, source_path), "segment concat")

        measurements = None
        if loudnorm:
            try:
                analysis = subprocess.run(
                    build_loudnorm_analysis_command(ffmpeg_path, source_path),
                    capture_output=True,
                    text=True,
                    timeout=3600,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
            except (OSError, subprocess.SubprocessError) as exc:
                raise PostProcessError(f"loudnorm analysis failed: {exc}") from exc
            measurements = parse_loudnorm_measurements(f"{analysis.stdout}\n{analysis.stderr}")
            if analysis.returncode != 0 or not measurements:
                raise PostProcessError("loudnorm analysis did not return usable measurements")
            emit("loudnorm analysis complete")

        if requires_processing:
            run_ffmpeg(
                build_postprocess_command(
                    ffmpeg_path,
                    source_path,
                    final_path,
                    h265=h265,
                    loudnorm_measurements=measurements,
                ),
                "final transcode",
            )
        emit(f"output: {final_path}")
        return final_path
    finally:
        if list_path:
            try:
                list_path.unlink()
            except FileNotFoundError:
                pass
        if requires_processing:
            try:
                source_path.unlink()
            except FileNotFoundError:
                pass
