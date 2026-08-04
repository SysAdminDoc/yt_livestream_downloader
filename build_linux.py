"""Build an unsigned Linux AppImage using PyInstaller and appimagetool."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path


def build_arguments(root: Path) -> list[str]:
    """Return the Linux PyInstaller one-file build arguments."""

    linux_build = root / "build" / "linux"
    linux_dist = root / "dist" / "linux" / "pyinstaller"
    return [
        "--noconfirm",
        "--clean",
        "--onefile",
        "--windowed",
        "--name",
        "YTLivestreamDownloader",
        "--icon",
        os.fspath(root / "icon.png"),
        "--add-data",
        f"{root / 'icon.png'}{os.pathsep}.",
        "--runtime-hook",
        os.fspath(root / "pyinstaller_runtime_hook.py"),
        "--paths",
        os.fspath(root),
        "--distpath",
        os.fspath(linux_dist),
        "--workpath",
        os.fspath(linux_build / "pyinstaller"),
        "--specpath",
        os.fspath(linux_build),
        os.fspath(root / "yt_livestream_downloader.py"),
    ]


def _write_appdir(appdir: Path, executable: Path, root: Path) -> None:
    binary = appdir / "usr" / "bin" / "YTLivestreamDownloader"
    binary.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(executable, binary)
    binary.chmod(0o755)
    shutil.copy2(root / "icon.png", appdir / "YTLivestreamDownloader.png")
    (appdir / "AppRun").write_text(
        '#!/bin/sh\nHERE="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"\nexec "$HERE/usr/bin/YTLivestreamDownloader" "$@"\n',
        encoding="utf-8",
        newline="\n",
    )
    (appdir / "AppRun").chmod(0o755)
    (appdir / "yt-livestream-downloader.desktop").write_text(
        "[Desktop Entry]\n"
        "Type=Application\n"
        "Name=YT Livestream Downloader\n"
        "Exec=YTLivestreamDownloader\n"
        "Icon=YTLivestreamDownloader\n"
        "Categories=AudioVideo;\n",
        encoding="utf-8",
        newline="\n",
    )


def build(root: Path, appimagetool: str | None = None) -> Path:
    """Build the Linux PyInstaller executable and wrap it as an AppImage."""

    root = root.resolve()
    appimagetool = appimagetool or shutil.which("appimagetool")
    if not appimagetool:
        raise RuntimeError("appimagetool is required on PATH")
    try:
        from PyInstaller.__main__ import run
    except ImportError as exc:
        raise RuntimeError("PyInstaller is required on the Linux build host") from exc

    linux_build = root / "build" / "linux"
    linux_dist = root / "dist" / "linux"
    appdir = linux_build / "YTLivestreamDownloader.AppDir"
    for target in (linux_build, linux_dist):
        if target.parent.parent != root:
            raise RuntimeError(f"refusing to clean outside the repository: {target}")
    if linux_build.exists():
        shutil.rmtree(linux_build)
    if linux_dist.exists():
        shutil.rmtree(linux_dist)
    linux_build.mkdir(parents=True, exist_ok=True)
    linux_dist.mkdir(parents=True, exist_ok=True)
    run(build_arguments(root))
    executable = linux_dist / "pyinstaller" / "YTLivestreamDownloader"
    if not executable.is_file() or executable.stat().st_size < 1024 * 1024:
        raise RuntimeError(f"PyInstaller did not produce a valid artifact: {executable}")
    _write_appdir(appdir, executable, root)
    output = root / "dist" / "YTLivestreamDownloader.AppImage"
    subprocess.check_call([appimagetool, os.fspath(appdir), os.fspath(output)])
    if not output.is_file() or output.stat().st_size < 1024 * 1024:
        raise RuntimeError(f"appimagetool did not produce a valid artifact: {output}")
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the unsigned Linux AppImage.")
    parser.add_argument("--dry-run", action="store_true", help="Print the PyInstaller argument list without building")
    parser.add_argument("--appimagetool", help="Path to appimagetool when it is not on PATH")
    args = parser.parse_args()
    root = Path(__file__).resolve().parent
    if args.dry_run:
        print(" ".join(build_arguments(root)))
        return 0
    try:
        artifact = build(root, args.appimagetool)
    except (OSError, RuntimeError, subprocess.CalledProcessError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    print(f"Built unsigned artifact: {artifact} ({artifact.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
