"""Generate release-ready WinGet and Scoop manifests for the Windows artifact."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from yt_livestream_core import APP_VERSION


PACKAGE_IDENTIFIER = "SysAdminDoc.YTLivestreamDownloader"
PACKAGE_NAME = "YT Livestream Downloader"
PUBLISHER = "SysAdminDoc"
REPOSITORY_URL = "https://github.com/SysAdminDoc/yt_livestream_downloader"
WINGET_MANIFEST_VERSION = "1.12.0"


def _validate_sha256(value: str) -> str:
    normalized = str(value).strip().lower()
    if not re.fullmatch(r"[0-9a-f]{64}", normalized):
        raise ValueError("SHA-256 must be exactly 64 hexadecimal characters")
    return normalized


def build_winget_documents(version: str, installer_url: str, sha256: str) -> dict[str, str]:
    """Return the three WinGet YAML documents for one portable x64 release."""

    version = str(version).strip()
    installer_url = str(installer_url).strip()
    sha256 = _validate_sha256(sha256)
    if not version or not installer_url:
        raise ValueError("version and installer URL are required")
    common = (
        f"PackageIdentifier: {PACKAGE_IDENTIFIER}\n"
        f"PackageVersion: {version}\n"
    )
    return {
        "version": (
            common
            + "DefaultLocale: en-US\n"
            "ManifestType: version\n"
            f"ManifestVersion: {WINGET_MANIFEST_VERSION}\n"
        ),
        "locale.en-US": (
            common
            + "PackageLocale: en-US\n"
            f"Publisher: {PUBLISHER}\n"
            f"PublisherUrl: {REPOSITORY_URL.rsplit('/', 1)[0]}\n"
            f"PackageName: {PACKAGE_NAME}\n"
            f"PackageUrl: {REPOSITORY_URL}\n"
            "License: MIT\n"
            f"LicenseUrl: {REPOSITORY_URL}/blob/main/LICENSE\n"
            "ShortDescription: Record livestreams as resilient timestamped segments.\n"
            "Description: A PyQt6 desktop and headless CLI recorder powered by yt-dlp, Streamlink, and ffmpeg.\n"
            "Moniker: yt-livestream-downloader\n"
            "Tags:\n"
            "- livestream\n"
            "- recorder\n"
            "- youtube\n"
            "- yt-dlp\n"
            "- streamlink\n"
            "ManifestType: defaultLocale\n"
            f"ManifestVersion: {WINGET_MANIFEST_VERSION}\n"
        ),
        "installer": (
            common
            + "Installers:\n"
            "- Architecture: x64\n"
            "  InstallerType: portable\n"
            f"  InstallerUrl: {installer_url}\n"
            f"  InstallerSha256: {sha256}\n"
            "  PortableCommandAlias: yt-livestream-downloader\n"
            "ManifestType: installer\n"
            f"ManifestVersion: {WINGET_MANIFEST_VERSION}\n"
        ),
    }


def build_scoop_manifest(version: str, installer_url: str, sha256: str) -> dict[str, object]:
    """Return a Scoop manifest for the unsigned portable Windows executable."""

    version = str(version).strip()
    installer_url = str(installer_url).strip()
    sha256 = _validate_sha256(sha256)
    if not version or not installer_url:
        raise ValueError("version and installer URL are required")
    return {
        "version": version,
        "description": "Record livestreams as resilient timestamped segments.",
        "homepage": REPOSITORY_URL,
        "license": "MIT",
        "architecture": {
            "64bit": {
                "url": installer_url,
                "hash": sha256,
                "bin": [["YTLivestreamDownloader.exe", "yt-livestream-downloader"]],
                "shortcuts": [["YTLivestreamDownloader.exe", PACKAGE_NAME]],
            }
        },
        "checkver": {"github": REPOSITORY_URL},
        "autoupdate": {
            "architecture": {
                "64bit": {
                    "url": f"{REPOSITORY_URL}/releases/download/v$version/YTLivestreamDownloader.exe"
                }
            }
        },
    }


def write_manifests(
    output_dir: str | Path,
    version: str,
    installer_url: str,
    sha256: str,
) -> list[Path]:
    """Write WinGet and Scoop manifests and return their paths."""

    root = Path(output_dir)
    winget_root = root / "winget" / PACKAGE_IDENTIFIER / str(version)
    scoop_root = root / "scoop"
    winget_root.mkdir(parents=True, exist_ok=True)
    scoop_root.mkdir(parents=True, exist_ok=True)
    documents = build_winget_documents(version, installer_url, sha256)
    paths = []
    for suffix, document in documents.items():
        path = winget_root / f"{PACKAGE_IDENTIFIER}.{suffix}.yaml"
        path.write_text(document, encoding="utf-8", newline="\n")
        paths.append(path)
    scoop_path = scoop_root / "yt-livestream-downloader.json"
    scoop_path.write_text(
        json.dumps(build_scoop_manifest(version, installer_url, sha256), indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    paths.append(scoop_path)
    return paths


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate WinGet and Scoop manifests for a release artifact.")
    parser.add_argument("--version", default=APP_VERSION)
    parser.add_argument("--installer-url", required=True)
    parser.add_argument("--sha256", required=True)
    parser.add_argument("--output", type=Path, default=Path("packaging"))
    args = parser.parse_args()
    try:
        paths = write_manifests(args.output, args.version, args.installer_url, args.sha256)
    except ValueError as exc:
        parser.error(str(exc))
    for path in paths:
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
