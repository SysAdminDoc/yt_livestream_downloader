"""Build the unsigned one-file Windows desktop artifact with PyInstaller."""

from __future__ import annotations

import argparse
import os
import shutil
from pathlib import Path


APP_NAME = "YTLivestreamDownloader"


def build_arguments(root: Path) -> list[str]:
    return [
        "--noconfirm",
        "--clean",
        "--onefile",
        "--windowed",
        "--name",
        APP_NAME,
        "--icon",
        os.fspath(root / "icon.ico"),
        "--add-data",
        f"{root / 'icon.png'}{os.pathsep}.",
        "--runtime-hook",
        os.fspath(root / "pyinstaller_runtime_hook.py"),
        "--paths",
        os.fspath(root),
        "--distpath",
        os.fspath(root / "dist"),
        "--workpath",
        os.fspath(root / "build"),
        "--specpath",
        os.fspath(root / "build"),
        os.fspath(root / "yt_livestream_downloader.py"),
    ]


def build(root: Path) -> Path:
    root = root.resolve()
    for name in ("build", "dist"):
        target = (root / name).resolve()
        if target.parent != root:
            raise RuntimeError(f"refusing to clean outside the repository: {target}")
        if target.exists():
            shutil.rmtree(target)
    from PyInstaller.__main__ import run

    run(build_arguments(root))
    artifact = root / "dist" / f"{APP_NAME}.exe"
    if not artifact.is_file() or artifact.stat().st_size < 1024 * 1024:
        raise RuntimeError(f"PyInstaller did not produce a valid artifact: {artifact}")
    return artifact


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the unsigned Windows one-file release artifact.")
    parser.add_argument("--dry-run", action="store_true", help="Print the PyInstaller argument list without building")
    args = parser.parse_args()
    root = Path(__file__).resolve().parent
    if args.dry_run:
        print(" ".join(build_arguments(root)))
        return 0
    artifact = build(root)
    print(f"Built unsigned artifact: {artifact} ({artifact.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
