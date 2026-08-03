"""Build a Linux AppImage using appimagetool on a Linux host."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path


def main() -> int:
    root = Path(__file__).resolve().parent
    appimagetool = shutil.which("appimagetool")
    if not appimagetool:
        print("appimagetool is required on PATH", file=sys.stderr)
        return 2
    appdir = root / "build" / "YTLivestreamDownloader.AppDir"
    appdir.mkdir(parents=True, exist_ok=True)
    desktop = appdir / "yt-livestream-downloader.desktop"
    desktop.write_text(
        "[Desktop Entry]\nType=Application\nName=YT Livestream Downloader\nExec=yt_livestream_downloader.py\nIcon=icon\nCategories=AudioVideo;Network;\n",
        encoding="utf-8",
    )
    subprocess.check_call([appimagetool, os.fspath(appdir), os.fspath(root / "dist" / "YTLivestreamDownloader.AppImage")])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
