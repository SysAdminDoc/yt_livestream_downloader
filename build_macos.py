"""Build the macOS application bundle with py2app on a macOS host."""

from __future__ import annotations

import sys


def main() -> int:
    try:
        from setuptools import setup
        import py2app  # noqa: F401
    except ImportError as exc:
        print(f"py2app is required on macOS: {exc}", file=sys.stderr)
        return 2
    setup(
        app=["yt_livestream_downloader.py"],
        data_files=["icon.png"],
        options={"py2app": {"argv_emulation": False, "packages": ["PyQt6"]}},
        setup_requires=["py2app"],
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
