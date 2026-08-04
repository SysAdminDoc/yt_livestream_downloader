"""Build the unsigned macOS application bundle with py2app on macOS."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from yt_livestream_core import APP_NAME, APP_VERSION


def build_setup_options(root: Path) -> dict[str, object]:
    """Return deterministic py2app options without invoking setuptools."""

    return {
        "app": [str(root / "yt_livestream_downloader.py")],
        "data_files": [str(root / "icon.png")],
        "options": {"py2app": {"argv_emulation": False, "packages": ["PyQt6"]}},
        "setup_requires": ["py2app"],
        "name": APP_NAME,
        "version": APP_VERSION,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the unsigned macOS app bundle with py2app.")
    parser.add_argument("--dry-run", action="store_true", help="Print the py2app configuration without building")
    args = parser.parse_args()
    root = Path(__file__).resolve().parent
    options = build_setup_options(root)
    if args.dry_run:
        print(options)
        return 0
    try:
        from setuptools import setup
        import py2app  # noqa: F401
    except ImportError as exc:
        print(f"py2app is required on macOS: {exc}", file=sys.stderr)
        return 2
    setup(**options)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
