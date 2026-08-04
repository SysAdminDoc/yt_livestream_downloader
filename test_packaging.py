import json
from pathlib import Path

from build_release import APP_NAME, build_arguments
from build_linux import build_arguments as build_linux_arguments
from build_macos import build_setup_options
from generate_manifests import build_scoop_manifest, build_winget_documents, write_manifests


def test_pyinstaller_arguments_are_one_file_windowed_and_unsigned():
    args = build_arguments(Path("C:/repo"))
    assert "--onefile" in args
    assert "--windowed" in args
    assert "--runtime-hook" in args
    assert "codesign_identity" not in " ".join(args)
    assert args[-1].endswith("yt_livestream_downloader.py")
    assert APP_NAME == "YTLivestreamDownloader"


def test_cross_platform_build_entrypoints_are_deterministic(tmp_path):
    linux_args = build_linux_arguments(tmp_path)
    assert "--onefile" in linux_args
    assert "--windowed" in linux_args
    assert linux_args[-1].endswith("yt_livestream_downloader.py")
    mac_options = build_setup_options(tmp_path)
    assert mac_options["app"] == [str(tmp_path / "yt_livestream_downloader.py")]
    assert mac_options["options"]["py2app"]["argv_emulation"] is False


def test_release_manifests_include_artifact_hash_and_update_paths(tmp_path):
    sha256 = "a" * 64
    url = "https://github.com/SysAdminDoc/yt_livestream_downloader/releases/download/v1.0.0/YTLivestreamDownloader.exe"
    documents = build_winget_documents("1.0.0", url, sha256)
    assert "InstallerSha256: " + sha256 in documents["installer"]
    scoop = build_scoop_manifest("1.0.0", url, sha256)
    assert scoop["architecture"]["64bit"]["hash"] == sha256
    paths = write_manifests(tmp_path, "1.0.0", url, sha256)
    assert len(paths) == 4
    loaded = json.loads((tmp_path / "scoop" / "yt-livestream-downloader.json").read_text(encoding="utf-8"))
    assert loaded["version"] == "1.0.0"
