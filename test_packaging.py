from pathlib import Path

from build_release import APP_NAME, build_arguments


def test_pyinstaller_arguments_are_one_file_windowed_and_unsigned():
    args = build_arguments(Path("C:/repo"))
    assert "--onefile" in args
    assert "--windowed" in args
    assert "--runtime-hook" in args
    assert "codesign_identity" not in " ".join(args)
    assert args[-1].endswith("yt_livestream_downloader.py")
    assert APP_NAME == "YTLivestreamDownloader"
