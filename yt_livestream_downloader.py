#!/usr/bin/env python3
"""
YouTube Livestream Downloader v1.0.0
Downloads YouTube livestreams in configurable time segments as separate files.
Uses yt-dlp + ffmpeg under the hood.
"""

import sys, os, subprocess, shutil, html
from pathlib import Path


# codex-branding:start
def _branding_icon_path() -> Path:
    candidates = []
    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).resolve().parent
        candidates.append(exe_dir / "icon.png")
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            candidates.append(Path(meipass) / "icon.png")
    current = Path(__file__).resolve()
    candidates.extend([current.parent / "icon.png", current.parent.parent / "icon.png", current.parent.parent.parent / "icon.png"])
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return Path("icon.png")
# codex-branding:end


def _bootstrap():
    """Auto-install dependencies before any imports."""
    if sys.version_info < (3, 8):
        print("Python 3.8+ required"); sys.exit(1)
    try:
        import pip
    except ImportError:
        subprocess.check_call([sys.executable, '-m', 'ensurepip', '--default-pip'])
    required = ['PyQt6', 'yt-dlp']
    for pkg in required:
        mod = pkg.split('[')[0].replace('-', '_').lower()
        try:
            __import__(mod)
        except ImportError:
            for flags in [[], ['--user'], ['--break-system-packages']]:
                try:
                    subprocess.check_call(
                        [sys.executable, '-m', 'pip', 'install', pkg, '-q'] + flags,
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    break
                except subprocess.CalledProcessError:
                    continue

_bootstrap()

import json, time, re, traceback
from datetime import datetime

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QSpinBox, QTextEdit, QFileDialog,
    QGroupBox, QGridLayout, QComboBox, QListWidget, QListWidgetItem,
    QSplitter, QStatusBar, QFrame, QCheckBox, QDateTimeEdit, QSizePolicy,
    QGraphicsOpacityEffect
)
from PyQt6.QtCore import (
    Qt, QThread, pyqtSignal, QTimer, QDateTime, QSize, QPropertyAnimation, QEasingCurve
)
from PyQt6.QtGui import QColor, QIcon, QPalette, QDesktopServices, QPixmap
from PyQt6.QtCore import QUrl

VERSION = "1.0.0"
APP_NAME = "YT Livestream Downloader"

THEME = {
    "bg": "#09111a",
    "surface": "#101a28",
    "surface_soft": "#0c1522",
    "surface_raised": "#132033",
    "border": "#22324a",
    "border_strong": "#314868",
    "text": "#f2f6ff",
    "text_soft": "#a7b6cc",
    "text_muted": "#6f809d",
    "accent": "#73b8ff",
    "success": "#63d59a",
    "warning": "#f2b862",
    "danger": "#ff7b7b",
    "info": "#77d9ff",
}

# ──────────────────────────────────────────────
# Config persistence
# ──────────────────────────────────────────────
def get_config_dir():
    base = os.environ.get('APPDATA', os.path.expanduser('~'))
    path = os.path.join(base, 'YTLivestreamDL')
    os.makedirs(path, exist_ok=True)
    return path

def load_config():
    cfg_file = os.path.join(get_config_dir(), 'config.json')
    try:
        with open(cfg_file) as f:
            return json.load(f)
    except Exception:
        return {}

def save_config(cfg):
    cfg_file = os.path.join(get_config_dir(), 'config.json')
    with open(cfg_file, 'w') as f:
        json.dump(cfg, f, indent=2)


def refresh_style(widget):
    widget.style().unpolish(widget)
    widget.style().polish(widget)
    widget.update()


def looks_like_youtube_url(value):
    return bool(re.search(r"(youtube\.com|youtu\.be)", value, re.IGNORECASE))


def format_when(dt):
    return dt.strftime("%a, %b %d at %I:%M %p")


def format_remaining(seconds):
    total = max(0, int(seconds))
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}h {minutes:02d}m {secs:02d}s"
    if minutes:
        return f"{minutes}m {secs:02d}s"
    return f"{secs}s"


def trim_path(path_str, max_length=58):
    if len(path_str) <= max_length:
        return path_str
    head = max_length // 2 - 2
    tail = max_length - head - 3
    return f"{path_str[:head]}...{path_str[-tail:]}"


def human_bytes(byte_count):
    if byte_count >= 1024 * 1024 * 1024:
        return f"{byte_count / (1024 * 1024 * 1024):.1f} GB"
    return f"{byte_count / (1024 * 1024):.1f} MB"


# ──────────────────────────────────────────────
# Premium Dark Theme
# ──────────────────────────────────────────────
DARK_STYLE = """
QMainWindow, QWidget { background-color: #09111a; color: #f2f6ff; }
QToolTip {
    background-color: #132033; color: #f2f6ff; border: 1px solid #314868; padding: 6px 8px;
}
QFrame#heroCard {
    background: qlineargradient(x1: 0, y1: 0, x2: 1, y2: 1,
        stop: 0 #0d1725, stop: 0.6 #101a29, stop: 1 #0b1320);
    border: 1px solid #22324a; border-radius: 24px;
}
QFrame#heroIconWrap {
    background-color: rgba(255, 255, 255, 0.03);
    border: 1px solid rgba(115, 184, 255, 0.18);
    border-radius: 18px;
}
QFrame#summaryCard {
    background-color: rgba(19, 32, 51, 0.92);
    border: 1px solid #22324a;
    border-radius: 18px;
}
QFrame#streamInfoCard {
    background-color: #101a28; border: 1px solid #22324a; border-radius: 16px;
}
QFrame#stateBanner {
    background-color: #0c1522; border: 1px solid #22324a; border-radius: 16px;
}
QFrame#stateBanner[tone="accent"] {
    background-color: rgba(115, 184, 255, 0.10); border-color: rgba(115, 184, 255, 0.35);
}
QFrame#stateBanner[tone="success"] {
    background-color: rgba(99, 213, 154, 0.10); border-color: rgba(99, 213, 154, 0.35);
}
QFrame#stateBanner[tone="info"] {
    background-color: rgba(119, 217, 255, 0.10); border-color: rgba(119, 217, 255, 0.34);
}
QFrame#stateBanner[tone="warning"] {
    background-color: rgba(242, 184, 98, 0.10); border-color: rgba(242, 184, 98, 0.35);
}
QFrame#stateBanner[tone="danger"] {
    background-color: rgba(255, 123, 123, 0.10); border-color: rgba(255, 123, 123, 0.35);
}
QGroupBox {
    background-color: #101a28;
    border: 1px solid #22324a; border-radius: 18px;
    margin-top: 1.1em; padding-top: 18px; color: #f2f6ff;
    font-weight: 600;
}
QGroupBox::title {
    subcontrol-origin: margin; left: 18px; padding: 0 8px;
    color: #f2f6ff; font-size: 14px;
}
QPushButton {
    border-radius: 12px; padding: 10px 16px; font-weight: 600; font-size: 13px;
}
QPushButton#primaryBtn {
    background-color: #73b8ff; color: #09111a; border: 1px solid transparent;
}
QPushButton#primaryBtn:hover { background-color: #8bc5ff; }
QPushButton#primaryBtn:pressed { background-color: #66adf9; }
QPushButton#primaryBtn:disabled {
    background-color: rgba(115, 184, 255, 0.25); color: rgba(9, 17, 26, 0.58);
}
QPushButton#stopBtn {
    background-color: rgba(255, 123, 123, 0.12); color: #ff9c9c;
    border: 1px solid rgba(255, 123, 123, 0.24);
}
QPushButton#stopBtn:hover { background-color: rgba(255, 123, 123, 0.18); }
QPushButton#stopBtn:disabled {
    background-color: rgba(255, 123, 123, 0.08); color: #8c6666;
    border-color: rgba(255, 123, 123, 0.14);
}
QPushButton#secondaryBtn, QPushButton#ghostBtn {
    background-color: #132033; color: #e8f1ff; border: 1px solid #273a55;
}
QPushButton#secondaryBtn:hover, QPushButton#ghostBtn:hover {
    background-color: #17283d; border-color: #314868;
}
QPushButton#secondaryBtn:pressed, QPushButton#ghostBtn:pressed { background-color: #1a3049; }
QPushButton#secondaryBtn:disabled, QPushButton#ghostBtn:disabled {
    background-color: #101925; color: #5e6f89; border-color: #1e2b3f;
}
QLineEdit, QSpinBox, QDateTimeEdit {
    background-color: #0c1522; color: #f2f6ff;
    border: 1px solid #22324a; border-radius: 12px; padding: 10px 12px;
    font-size: 13px; selection-background-color: #73b8ff; selection-color: #09111a;
}
QLineEdit[state="warning"] { border-color: rgba(242, 184, 98, 0.56); background-color: #121b28; }
QLineEdit:focus, QSpinBox:focus, QDateTimeEdit:focus, QComboBox:focus { border-color: #73b8ff; }
QComboBox {
    background-color: #0c1522; color: #f2f6ff;
    border: 1px solid #22324a; border-radius: 12px; padding: 10px 12px;
    font-size: 13px;
}
QComboBox::drop-down, QDateTimeEdit::drop-down { border: none; width: 26px; }
QComboBox::down-arrow {
    image: none; border-left: 5px solid transparent;
    border-right: 5px solid transparent; border-top: 6px solid #a7b6cc;
    margin-right: 6px;
}
QComboBox QAbstractItemView {
    background-color: #132033; color: #f2f6ff;
    border: 1px solid #314868; selection-background-color: rgba(115, 184, 255, 0.24);
    selection-color: #f2f6ff; outline: none;
}
QTextEdit {
    background-color: #0c1522; color: #d7e4f7;
    border: 1px solid #22324a; border-radius: 16px; padding: 10px 12px;
    font-family: 'Cascadia Code', 'Consolas', 'Courier New', monospace;
    font-size: 12px;
}
QListWidget {
    background-color: #0c1522; color: #f2f6ff;
    border: 1px solid #22324a; border-radius: 16px; padding: 8px;
    font-size: 12px; outline: none;
}
QListWidget::item { padding: 8px 10px; border-radius: 12px; }
QListWidget::item:selected { background-color: rgba(115, 184, 255, 0.13); color: #f2f6ff; }
QListWidget::item:hover { background-color: rgba(115, 184, 255, 0.07); }
QLabel { color: #f2f6ff; }
QLabel#eyebrowLabel {
    color: #73b8ff; font-size: 11px; font-weight: 700; letter-spacing: 0.18em;
}
QLabel#titleLabel { font-size: 28px; font-weight: 700; color: #f7fbff; }
QLabel#subtitleLabel { font-size: 14px; color: #a7b6cc; }
QLabel#summaryKicker {
    color: #6f809d; font-size: 11px; font-weight: 700; letter-spacing: 0.14em;
}
QLabel#summaryTitle { color: #f2f6ff; font-size: 15px; font-weight: 600; }
QLabel#sectionLabel { font-size: 13px; color: #a7b6cc; font-weight: 600; }
QLabel#fieldLabel { color: #dbe7fb; font-size: 12px; font-weight: 600; }
QLabel#helperLabel { color: #7f92ad; font-size: 12px; }
QLabel#statValue { font-size: 22px; font-weight: 700; color: #73b8ff; }
QLabel#statValue[tone="neutral"] { color: #f2f6ff; }
QLabel#statValue[tone="accent"] { color: #73b8ff; }
QLabel#statValue[tone="success"] { color: #63d59a; }
QLabel#statValue[tone="warning"] { color: #f2b862; }
QLabel#statValue[tone="danger"] { color: #ff7b7b; }
QLabel#statValue[tone="info"] { color: #77d9ff; }
QLabel#statLabel {
    font-size: 11px; color: #6f809d; font-weight: 600; letter-spacing: 0.08em;
}
QLabel#streamTitle { font-size: 17px; font-weight: 600; color: #f2f6ff; }
QLabel#streamMeta { font-size: 13px; color: #bfd0e8; }
QLabel#streamHint { font-size: 12px; color: #7f92ad; }
QLabel#badge {
    border-radius: 999px; padding: 5px 10px; font-size: 11px; font-weight: 700;
}
QLabel#badge[tone="neutral"] {
    background-color: rgba(115, 128, 157, 0.14); border: 1px solid rgba(115, 128, 157, 0.25); color: #a7b6cc;
}
QLabel#badge[tone="accent"] {
    background-color: rgba(115, 184, 255, 0.14); border: 1px solid rgba(115, 184, 255, 0.28); color: #8bc5ff;
}
QLabel#badge[tone="success"] {
    background-color: rgba(99, 213, 154, 0.16); border: 1px solid rgba(99, 213, 154, 0.28); color: #7ae3ad;
}
QLabel#badge[tone="warning"] {
    background-color: rgba(242, 184, 98, 0.16); border: 1px solid rgba(242, 184, 98, 0.28); color: #f7c57e;
}
QLabel#badge[tone="danger"] {
    background-color: rgba(255, 123, 123, 0.16); border: 1px solid rgba(255, 123, 123, 0.28); color: #ff9494;
}
QLabel#badge[tone="info"] {
    background-color: rgba(119, 217, 255, 0.15); border: 1px solid rgba(119, 217, 255, 0.28); color: #98e3ff;
}
QLabel#statusTitle { color: #f2f6ff; font-size: 15px; font-weight: 600; }
QLabel#statusDetail { color: #a7b6cc; font-size: 12px; }
QLabel#emptyState {
    color: #7f92ad; font-size: 13px; padding: 26px 18px;
    border: 1px dashed #273a55; border-radius: 16px; background-color: #0c1522;
}
QCheckBox { color: #e6eefc; spacing: 8px; font-size: 13px; }
QCheckBox::indicator {
    width: 18px; height: 18px; border-radius: 5px;
    border: 1px solid #314868; background: #0c1522;
}
QCheckBox::indicator:checked { background: #73b8ff; border-color: #73b8ff; }
QStatusBar { background-color: #0c1522; color: #7f92ad; font-size: 12px; border-top: 1px solid #1a2638; }
QStatusBar::item { border: none; }
QSplitter::handle { background-color: transparent; }
QFrame#separator { background-color: #22324a; }
QFrame#statCard {
    background-color: #0c1522; border: 1px solid #22324a; border-radius: 16px;
    padding: 8px;
}
QFrame#toast {
    background-color: rgba(12, 21, 34, 0.98);
    border: 1px solid #314868; border-radius: 16px;
}
QScrollBar:vertical { background: transparent; width: 12px; border: none; margin: 4px 0; }
QScrollBar::handle:vertical { background: rgba(115, 128, 157, 0.45); border-radius: 6px; min-height: 30px; }
QScrollBar::handle:vertical:hover { background: rgba(115, 184, 255, 0.5); }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
"""


# ──────────────────────────────────────────────
# Status Badge
# ──────────────────────────────────────────────
class StatusBadge(QLabel):
    def __init__(self, text="", tone="neutral", parent=None):
        super().__init__(text, parent)
        self.setObjectName("badge")
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        self.set_status(text, tone)

    def set_status(self, text, tone):
        self.setText(text)
        self.setProperty("tone", tone)
        refresh_style(self)


# ──────────────────────────────────────────────
# Toast Notification Widget
# ──────────────────────────────────────────────
class ToastNotification(QFrame):
    """A gently animated toast notification."""
    def __init__(self, parent, message, tone="success", duration_ms=3400):
        super().__init__(parent)
        self.setObjectName("toast")
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(10)

        badge = StatusBadge("Saved" if tone == "success" else "Notice", tone)
        text = QLabel(message)
        text.setObjectName("helperLabel")
        text.setWordWrap(True)

        layout.addWidget(badge, 0, Qt.AlignmentFlag.AlignTop)
        layout.addWidget(text, 1)

        self.opacity_effect = QGraphicsOpacityEffect(self)
        self.opacity_effect.setOpacity(0.0)
        self.setGraphicsEffect(self.opacity_effect)

        self.adjustSize()
        px = max(20, parent.width() - self.width() - 24)
        self.move(px, 24)
        self.show()
        self.raise_()

        self.fade_in = QPropertyAnimation(self.opacity_effect, b"opacity", self)
        self.fade_in.setDuration(180)
        self.fade_in.setStartValue(0.0)
        self.fade_in.setEndValue(1.0)
        self.fade_in.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.fade_in.start()
        QTimer.singleShot(duration_ms, self._fade_out)

    def _fade_out(self):
        self.fade_out = QPropertyAnimation(self.opacity_effect, b"opacity", self)
        self.fade_out.setDuration(220)
        self.fade_out.setStartValue(1.0)
        self.fade_out.setEndValue(0.0)
        self.fade_out.setEasingCurve(QEasingCurve.Type.InCubic)
        self.fade_out.finished.connect(self.deleteLater)
        self.fade_out.start()


# ──────────────────────────────────────────────
# Dependency Checker
# ──────────────────────────────────────────────
def check_dependency(name):
    """Check if a CLI tool exists and return its version string or None."""
    try:
        if name == 'yt-dlp':
            path = shutil.which('yt-dlp')
            if path:
                r = subprocess.run([path, '--version'], capture_output=True, text=True, timeout=10)
                return r.stdout.strip() if r.returncode == 0 else None
            r = subprocess.run(
                [sys.executable, '-m', 'yt_dlp', '--version'],
                capture_output=True, text=True, timeout=10)
            return r.stdout.strip() if r.returncode == 0 else None
        else:
            path = shutil.which(name)
            if not path:
                return None
            r = subprocess.run([path, '-version'], capture_output=True, text=True, timeout=10)
            for line in r.stdout.split('\n'):
                if 'version' in line.lower():
                    return line.strip()
            return "installed"
    except Exception:
        return None


# ──────────────────────────────────────────────
# Stream Info Fetcher
# ──────────────────────────────────────────────
class StreamInfoWorker(QThread):
    """Fetch stream metadata without blocking the GUI."""
    info_ready = pyqtSignal(dict)
    error = pyqtSignal(str)

    def __init__(self, url, ytdlp_cmd, parent=None):
        super().__init__(parent)
        self.url = url
        self.ytdlp_cmd = ytdlp_cmd

    def run(self):
        try:
            cmd = self.ytdlp_cmd + ['--dump-json', '--no-download', self.url]
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=30,
                               creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0)
            if r.returncode == 0 and r.stdout.strip():
                info = json.loads(r.stdout.strip().split('\n')[0])
                self.info_ready.emit(info)
            else:
                self.error.emit(r.stderr.strip() or "Failed to fetch stream info")
        except subprocess.TimeoutExpired:
            self.error.emit("Stream info fetch timed out")
        except Exception as e:
            self.error.emit(str(e))


# ──────────────────────────────────────────────
# Segment Download Worker
# ──────────────────────────────────────────────
class SegmentDownloader(QThread):
    """Downloads a livestream in timed segments using yt-dlp."""
    log_message = pyqtSignal(str)
    segment_complete = pyqtSignal(str, float)  # filepath, size_bytes
    status_update = pyqtSignal(str)
    error = pyqtSignal(str)
    finished_all = pyqtSignal()

    def __init__(self, url, output_dir, segment_minutes, quality, max_retries=3,
                 retry_delay=10, filename_prefix="", parent=None):
        super().__init__(parent)
        self.url = url
        self.output_dir = output_dir
        self.segment_minutes = segment_minutes
        self.quality = quality
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.filename_prefix = filename_prefix
        self._stop_requested = False
        self._current_process = None

    def request_stop(self):
        self._stop_requested = True
        if self._current_process:
            try:
                self._current_process.terminate()
            except Exception:
                pass

    def _get_ytdlp_cmd(self):
        path = shutil.which('yt-dlp')
        if path:
            return [path]
        return [sys.executable, '-m', 'yt_dlp']

    def _sanitize_filename(self, name):
        """Clean a string for safe use as a filename."""
        name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', name)
        name = re.sub(r'[.\s]+$', '', name)
        name = re.sub(r'_+', '_', name)
        return name[:80].strip('_ ')

    def run(self):
        try:
            ytdlp_cmd = self._get_ytdlp_cmd()
            self.log_message.emit(f"yt-dlp: {' '.join(ytdlp_cmd)}")
            self.log_message.emit(f"Output: {self.output_dir}")
            self.log_message.emit(f"Segments: {self.segment_minutes} min | Quality: {self.quality}")
            self.log_message.emit(f"Retries: {self.max_retries} (delay {self.retry_delay}s)")

            # Get stream title for filenames
            self.status_update.emit("Fetching stream info...")
            safe_title = self.filename_prefix or "livestream"

            if not self.filename_prefix:
                try:
                    info_cmd = ytdlp_cmd + ['--dump-json', '--no-download', self.url]
                    r = subprocess.run(info_cmd, capture_output=True, text=True, timeout=30,
                                       creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0)
                    if r.returncode == 0 and r.stdout.strip():
                        info = json.loads(r.stdout.strip().split('\n')[0])
                        safe_title = self._sanitize_filename(info.get('title', 'livestream'))
                except Exception:
                    pass

            os.makedirs(self.output_dir, exist_ok=True)
            segment_num = 1
            segment_secs = self.segment_minutes * 60
            consecutive_failures = 0

            # Format selection
            format_map = {
                "Best": None,
                "1080p": "b[height<=1080]/bv[height<=1080]+ba/b",
                "720p": "b[height<=720]/bv[height<=720]+ba/b",
                "480p": "b[height<=480]/bv[height<=480]+ba/b",
                "Audio Only": "ba/b",
            }
            fmt = format_map.get(self.quality)

            while not self._stop_requested:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                ext = "m4a" if self.quality == "Audio Only" else "mp4"
                filename = f"{safe_title}_seg{segment_num:03d}_{timestamp}.{ext}"
                filepath = os.path.join(self.output_dir, filename)

                self.status_update.emit(f"Recording segment {segment_num}...")
                self.log_message.emit(f"\n--- Segment {segment_num} | {datetime.now().strftime('%H:%M:%S')} ---")
                self.log_message.emit(f"File: {filename}")

                cmd = ytdlp_cmd + [
                    '--downloader', 'ffmpeg',
                    '--downloader-args', f'ffmpeg:-t {segment_secs}',
                    '-o', filepath,
                    '--no-part',
                    '--newline',
                ]
                if fmt:
                    cmd += ['-f', fmt]
                cmd.append(self.url)

                success = False
                for attempt in range(self.max_retries + 1):
                    if self._stop_requested:
                        break

                    if attempt > 0:
                        self.log_message.emit(f"Retry {attempt}/{self.max_retries} in {self.retry_delay}s...")
                        self.status_update.emit(f"Retrying segment {segment_num} ({attempt}/{self.max_retries})...")
                        for _ in range(self.retry_delay * 10):
                            if self._stop_requested:
                                break
                            time.sleep(0.1)
                        if self._stop_requested:
                            break
                        if os.path.isfile(filepath):
                            try:
                                os.remove(filepath)
                            except OSError:
                                pass

                    try:
                        self._current_process = subprocess.Popen(
                            cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            text=True, bufsize=1,
                            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0
                        )

                        start_time = time.time()
                        for line in iter(self._current_process.stdout.readline, ''):
                            if self._stop_requested:
                                break
                            line = line.strip()
                            if line:
                                if any(k in line.lower() for k in [
                                    'download', 'error', 'warning', 'merge',
                                    'frame', 'size', '%', 'fragment'
                                ]):
                                    self.log_message.emit(line)
                                elapsed = time.time() - start_time
                                mins = int(elapsed // 60)
                                secs = int(elapsed % 60)
                                self.status_update.emit(
                                    f"Segment {segment_num} | "
                                    f"{mins:02d}:{secs:02d} / {self.segment_minutes:02d}:00"
                                )

                        self._current_process.wait(timeout=15)
                        retcode = self._current_process.returncode
                        self._current_process = None

                        if os.path.isfile(filepath) and os.path.getsize(filepath) > 1024:
                            success = True
                            break
                        elif retcode != 0 and not self._stop_requested:
                            self.log_message.emit(f"yt-dlp exited with code {retcode}")

                    except subprocess.TimeoutExpired:
                        if self._current_process:
                            self._current_process.kill()
                        self._current_process = None
                        self.log_message.emit("Process timed out")
                    except Exception as e:
                        self._current_process = None
                        self.log_message.emit(f"Error: {e}")

                if self._stop_requested:
                    self.log_message.emit("\nStopped by user.")
                    if os.path.isfile(filepath) and os.path.getsize(filepath) > 1024:
                        size = os.path.getsize(filepath)
                        self.log_message.emit(f"Partial segment saved: {filename}")
                        self.segment_complete.emit(filepath, size)
                    break

                if success:
                    size = os.path.getsize(filepath)
                    size_mb = size / (1024 * 1024)
                    self.log_message.emit(f"Segment {segment_num} complete: {size_mb:.1f} MB")
                    self.segment_complete.emit(filepath, size)
                    segment_num += 1
                    consecutive_failures = 0
                else:
                    consecutive_failures += 1
                    self.log_message.emit(
                        f"Segment {segment_num} failed after {self.max_retries + 1} attempts.")
                    if os.path.isfile(filepath):
                        try:
                            os.remove(filepath)
                        except OSError:
                            pass
                    if consecutive_failures >= 3:
                        self.log_message.emit("3 consecutive failures. Stream likely ended.")
                        break
                    self.log_message.emit("Retrying next segment...")

            self.finished_all.emit()
        except Exception as e:
            self.error.emit(f"{type(e).__name__}: {e}\n{traceback.format_exc()}")
            self.finished_all.emit()


# ──────────────────────────────────────────────
# Stat Card Widget
# ──────────────────────────────────────────────
class StatCard(QFrame):
    def __init__(self, label_text, initial_value="0", tone="accent"):
        super().__init__()
        self.setObjectName("statCard")
        self.setFixedHeight(84)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(6)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.value_label = QLabel(initial_value)
        self.value_label.setObjectName("statValue")
        self.value_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.desc_label = QLabel(label_text)
        self.desc_label.setObjectName("statLabel")
        self.desc_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        layout.addWidget(self.value_label)
        layout.addWidget(self.desc_label)
        self.set_tone(tone)

    def set_value(self, val):
        self.value_label.setText(str(val))

    def set_tone(self, tone):
        self.value_label.setProperty("tone", tone)
        refresh_style(self.value_label)


# ──────────────────────────────────────────────
# Main Window
# ──────────────────────────────────────────────
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"{APP_NAME} v{VERSION}")
        self.setMinimumSize(980, 760)
        self.resize(1220, 860)
        self.worker = None
        self.info_worker = None
        self._schedule_timer = QTimer(self)
        self._schedule_timer.timeout.connect(self._check_scheduled_start)
        self._elapsed_timer = QTimer(self)
        self._elapsed_timer.timeout.connect(self._update_elapsed)
        self._recording_start = None
        self._total_bytes = 0
        self._segment_count = 0
        self._stream_info = None
        self._segment_paths = []
        self._session_locked = False
        self._session_error = False
        self._user_stopped = False
        self._previewed_url = None
        self._ffmpeg_ok = False
        self._ytdlp_ok = False

        self._config = load_config()
        self._default_output = self._config.get(
            'output_dir', str(Path.home() / "Downloads" / "YT_Livestreams"))

        self._build_ui()
        self._connect_signals()
        self._restore_settings()
        self._check_deps()
        self._sync_segment_state()
        self._set_stream_preview_placeholder()
        self._refresh_descriptions()
        self._refresh_url_guidance()
        self._refresh_action_availability()
        self._refresh_idle_state()

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(22, 22, 22, 16)
        layout.setSpacing(16)

        hero_card = QFrame()
        hero_card.setObjectName("heroCard")
        hero_layout = QHBoxLayout(hero_card)
        hero_layout.setContentsMargins(22, 20, 22, 20)
        hero_layout.setSpacing(22)

        brand_layout = QHBoxLayout()
        brand_layout.setSpacing(16)

        icon_wrap = QFrame()
        icon_wrap.setObjectName("heroIconWrap")
        icon_wrap.setFixedSize(88, 88)
        icon_layout = QVBoxLayout(icon_wrap)
        icon_layout.setContentsMargins(8, 8, 8, 8)
        icon_label = QLabel()
        icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        pixmap = QPixmap(str(_branding_icon_path()))
        if not pixmap.isNull():
            icon_label.setPixmap(
                pixmap.scaled(68, 68, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            )
        icon_layout.addWidget(icon_label)
        brand_layout.addWidget(icon_wrap)

        title_col = QVBoxLayout()
        title_col.setSpacing(8)
        eyebrow = QLabel("STREAM CAPTURE WORKSPACE")
        eyebrow.setObjectName("eyebrowLabel")
        title = QLabel(APP_NAME)
        title.setObjectName("titleLabel")
        subtitle = QLabel(
            "Record YouTube livestreams as clean, timestamped segments with scheduled starts, calmer retries, and clearer session feedback."
        )
        subtitle.setObjectName("subtitleLabel")
        subtitle.setWordWrap(True)

        badge_row = QHBoxLayout()
        badge_row.setSpacing(8)
        self.readiness_badge = StatusBadge("Idle", "neutral")
        self.dep_ytdlp_label = StatusBadge("yt-dlp: checking", "neutral")
        self.dep_ffmpeg_label = StatusBadge("ffmpeg: checking", "neutral")
        badge_row.addWidget(self.readiness_badge)
        badge_row.addWidget(self.dep_ytdlp_label)
        badge_row.addWidget(self.dep_ffmpeg_label)
        badge_row.addStretch()

        title_col.addWidget(eyebrow)
        title_col.addWidget(title)
        title_col.addWidget(subtitle)
        title_col.addLayout(badge_row)
        brand_layout.addLayout(title_col, 1)
        hero_layout.addLayout(brand_layout, 3)

        summary_card = QFrame()
        summary_card.setObjectName("summaryCard")
        summary_layout = QVBoxLayout(summary_card)
        summary_layout.setContentsMargins(18, 16, 18, 16)
        summary_layout.setSpacing(10)
        summary_kicker = QLabel("Current setup")
        summary_kicker.setObjectName("summaryKicker")
        self.hero_summary_label = QLabel("")
        self.hero_summary_label.setObjectName("summaryTitle")
        self.hero_summary_label.setWordWrap(True)
        self.hero_schedule_label = QLabel("")
        self.hero_schedule_label.setObjectName("helperLabel")
        self.hero_schedule_label.setWordWrap(True)
        self.hero_output_label = QLabel("")
        self.hero_output_label.setObjectName("helperLabel")
        self.hero_output_label.setWordWrap(True)
        summary_layout.addWidget(summary_kicker)
        summary_layout.addWidget(self.hero_summary_label)
        summary_layout.addWidget(self.hero_schedule_label)
        summary_layout.addWidget(self.hero_output_label)
        summary_layout.addStretch()
        hero_layout.addWidget(summary_card, 2)
        layout.addWidget(hero_card)

        sep = QFrame(); sep.setObjectName("separator"); sep.setFixedHeight(1)
        layout.addWidget(sep)

        # ── Stream Preview Bar ──
        self.stream_info_frame = QFrame()
        self.stream_info_frame.setObjectName("streamInfoCard")
        si_layout = QHBoxLayout(self.stream_info_frame)
        si_layout.setContentsMargins(16, 14, 16, 14)
        si_layout.setSpacing(14)
        preview_copy = QVBoxLayout()
        preview_copy.setSpacing(6)
        self.stream_title_label = QLabel("")
        self.stream_title_label.setObjectName("streamTitle")
        self.stream_title_label.setWordWrap(True)
        self.stream_meta_label = QLabel("")
        self.stream_meta_label.setObjectName("streamMeta")
        self.stream_meta_label.setWordWrap(True)
        self.stream_hint_label = QLabel("")
        self.stream_hint_label.setObjectName("streamHint")
        self.stream_hint_label.setWordWrap(True)
        preview_copy.addWidget(self.stream_title_label)
        preview_copy.addWidget(self.stream_meta_label)
        preview_copy.addWidget(self.stream_hint_label)
        si_layout.addLayout(preview_copy, 1)

        preview_badges = QVBoxLayout()
        preview_badges.setSpacing(8)
        preview_badges.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignRight)
        self.stream_preview_badge = StatusBadge("Awaiting preview", "neutral")
        self.stream_live_label = StatusBadge("Status unknown", "neutral")
        self.stream_filename_badge = StatusBadge("Filename auto", "neutral")
        preview_badges.addWidget(self.stream_preview_badge)
        preview_badges.addWidget(self.stream_live_label)
        preview_badges.addWidget(self.stream_filename_badge)
        si_layout.addLayout(preview_badges)
        layout.addWidget(self.stream_info_frame)

        # ── Stream Settings ──
        stream_group = QGroupBox("Stream Settings")
        sg = QGridLayout(stream_group)
        sg.setContentsMargins(18, 24, 18, 16)
        sg.setHorizontalSpacing(12)
        sg.setVerticalSpacing(10)

        url_label = QLabel("Livestream URL")
        url_label.setObjectName("fieldLabel")
        sg.addWidget(url_label, 0, 0)
        self.url_input = QLineEdit()
        self.url_input.setClearButtonEnabled(True)
        self.url_input.setPlaceholderText("https://www.youtube.com/watch?v=... or https://youtu.be/...")
        sg.addWidget(self.url_input, 0, 1, 1, 2)
        self.fetch_info_btn = QPushButton("Preview stream")
        self.fetch_info_btn.setObjectName("secondaryBtn")
        self.fetch_info_btn.setFixedWidth(140)
        self.fetch_info_btn.setFixedHeight(42)
        sg.addWidget(self.fetch_info_btn, 0, 3)

        self.url_hint_label = QLabel("")
        self.url_hint_label.setObjectName("helperLabel")
        self.url_hint_label.setWordWrap(True)
        sg.addWidget(self.url_hint_label, 1, 1, 1, 3)

        output_label = QLabel("Output folder")
        output_label.setObjectName("fieldLabel")
        sg.addWidget(output_label, 2, 0)
        self.output_input = QLineEdit(self._default_output)
        sg.addWidget(self.output_input, 2, 1, 1, 2)
        self.browse_btn = QPushButton("Choose folder")
        self.browse_btn.setObjectName("secondaryBtn")
        self.browse_btn.setFixedWidth(140)
        self.browse_btn.setFixedHeight(42)
        sg.addWidget(self.browse_btn, 2, 3)

        self.output_hint_label = QLabel("")
        self.output_hint_label.setObjectName("helperLabel")
        self.output_hint_label.setWordWrap(True)
        sg.addWidget(self.output_hint_label, 3, 1, 1, 3)

        segment_label = QLabel("Segment length")
        segment_label.setObjectName("fieldLabel")
        sg.addWidget(segment_label, 4, 0)
        self.segment_spin = QSpinBox()
        self.segment_spin.setRange(1, 360)
        self.segment_spin.setValue(30)
        self.segment_spin.setSuffix(" min")
        self.segment_spin.setFixedWidth(140)
        sg.addWidget(self.segment_spin, 4, 1)

        quality_label = QLabel("Quality")
        quality_label.setObjectName("fieldLabel")
        sg.addWidget(quality_label, 4, 2, Qt.AlignmentFlag.AlignRight)
        self.quality_combo = QComboBox()
        self.quality_combo.addItems(["Best", "1080p", "720p", "480p", "Audio Only"])
        self.quality_combo.setFixedWidth(140)
        sg.addWidget(self.quality_combo, 4, 3)

        retries_label = QLabel("Retries / segment")
        retries_label.setObjectName("fieldLabel")
        sg.addWidget(retries_label, 5, 0)
        self.retries_spin = QSpinBox()
        self.retries_spin.setRange(0, 20)
        self.retries_spin.setValue(3)
        self.retries_spin.setFixedWidth(140)
        self.retries_spin.setToolTip("Max retry attempts per segment on failure")
        sg.addWidget(self.retries_spin, 5, 1)

        self.schedule_check = QCheckBox("Start later")
        self.schedule_check.setToolTip("Delay recording until a specific time")
        sg.addWidget(self.schedule_check, 5, 2, Qt.AlignmentFlag.AlignRight)
        self.schedule_dt = QDateTimeEdit(QDateTime.currentDateTime().addSecs(3600))
        self.schedule_dt.setDisplayFormat("ddd, MMM d  hh:mm ap")
        self.schedule_dt.setCalendarPopup(True)
        self.schedule_dt.setEnabled(False)
        self.schedule_dt.setFixedWidth(190)
        sg.addWidget(self.schedule_dt, 5, 3)

        self.capture_summary_label = QLabel("")
        self.capture_summary_label.setObjectName("helperLabel")
        self.capture_summary_label.setWordWrap(True)
        sg.addWidget(self.capture_summary_label, 6, 0, 1, 4)

        self.schedule_summary_label = QLabel("")
        self.schedule_summary_label.setObjectName("helperLabel")
        self.schedule_summary_label.setWordWrap(True)
        sg.addWidget(self.schedule_summary_label, 7, 0, 1, 4)

        sg.setColumnStretch(1, 1)
        layout.addWidget(stream_group)

        # ── State Banner ──
        self.state_banner = QFrame()
        self.state_banner.setObjectName("stateBanner")
        self.state_banner.setProperty("tone", "neutral")
        state_layout = QVBoxLayout(self.state_banner)
        state_layout.setContentsMargins(16, 14, 16, 14)
        state_layout.setSpacing(8)
        state_row = QHBoxLayout()
        state_row.setSpacing(8)
        self.state_badge = StatusBadge("Idle", "neutral")
        state_row.addWidget(self.state_badge)
        state_row.addStretch()
        self.state_title_label = QLabel("")
        self.state_title_label.setObjectName("statusTitle")
        self.state_title_label.setWordWrap(True)
        self.state_detail_label = QLabel("")
        self.state_detail_label.setObjectName("statusDetail")
        self.state_detail_label.setWordWrap(True)
        state_layout.addLayout(state_row)
        state_layout.addWidget(self.state_title_label)
        state_layout.addWidget(self.state_detail_label)
        layout.addWidget(self.state_banner)

        # ── Stats Row ──
        stats_layout = QHBoxLayout()
        stats_layout.setSpacing(10)
        self.stat_segments = StatCard("Segments captured", "0", "accent")
        self.stat_size = StatCard("Total saved", "0 MB", "accent")
        self.stat_elapsed = StatCard("Elapsed", "00:00", "accent")
        self.stat_status = StatCard("State", "Idle", "neutral")
        stats_layout.addWidget(self.stat_segments)
        stats_layout.addWidget(self.stat_size)
        stats_layout.addWidget(self.stat_elapsed)
        stats_layout.addWidget(self.stat_status)
        layout.addLayout(stats_layout)

        # ── Controls ──
        ctrl = QHBoxLayout()
        ctrl.setSpacing(12)

        self.start_btn = QPushButton("Start session")
        self.start_btn.setObjectName("primaryBtn")
        self.start_btn.setFixedHeight(44)
        self.start_btn.setCursor(Qt.CursorShape.PointingHandCursor)

        self.stop_btn = QPushButton("Stop session")
        self.stop_btn.setObjectName("stopBtn")
        self.stop_btn.setFixedHeight(44)
        self.stop_btn.setFixedWidth(136)
        self.stop_btn.setEnabled(False)
        self.stop_btn.setCursor(Qt.CursorShape.PointingHandCursor)

        self.open_folder_btn = QPushButton("Open captures")
        self.open_folder_btn.setObjectName("ghostBtn")
        self.open_folder_btn.setFixedHeight(44)
        self.open_folder_btn.setFixedWidth(150)
        self.open_folder_btn.setCursor(Qt.CursorShape.PointingHandCursor)

        ctrl.addWidget(self.start_btn)
        ctrl.addWidget(self.stop_btn)
        ctrl.addStretch()
        ctrl.addWidget(self.open_folder_btn)
        layout.addLayout(ctrl)

        # ── Splitter: Segments + Log ──
        splitter = QSplitter(Qt.Orientation.Horizontal)

        seg_widget = QWidget()
        seg_layout = QVBoxLayout(seg_widget)
        seg_layout.setContentsMargins(0, 0, 0, 0)
        seg_layout.setSpacing(6)
        seg_header = QHBoxLayout()
        seg_label = QLabel("Recorded Segments")
        seg_label.setObjectName("sectionLabel")
        self.segment_count_badge = StatusBadge("0 saved", "neutral")
        seg_header.addWidget(seg_label)
        seg_header.addStretch()
        seg_header.addWidget(self.segment_count_badge)
        seg_layout.addLayout(seg_header)
        self.segment_empty_label = QLabel(
            "No segments yet. Finished recordings appear here automatically and can be opened with a double-click."
        )
        self.segment_empty_label.setObjectName("emptyState")
        self.segment_empty_label.setWordWrap(True)
        seg_layout.addWidget(self.segment_empty_label)
        self.segment_list = QListWidget()
        self.segment_list.setAlternatingRowColors(False)
        self.segment_list.setVisible(False)
        seg_layout.addWidget(self.segment_list)

        log_widget = QWidget()
        log_layout = QVBoxLayout(log_widget)
        log_layout.setContentsMargins(0, 0, 0, 0)
        log_layout.setSpacing(6)

        log_header = QHBoxLayout()
        log_label = QLabel("Activity Log")
        log_label.setObjectName("sectionLabel")
        log_header.addWidget(log_label)
        log_header.addStretch()
        self.clear_log_btn = QPushButton("Clear log")
        self.clear_log_btn.setObjectName("secondaryBtn")
        self.clear_log_btn.setFixedSize(90, 34)
        log_header.addWidget(self.clear_log_btn)
        log_layout.addLayout(log_header)
        log_hint = QLabel("Retries, download progress, and saved segments are timestamped here for quick diagnosis.")
        log_hint.setObjectName("helperLabel")
        log_hint.setWordWrap(True)
        log_layout.addWidget(log_hint)

        self.log_output = QTextEdit()
        self.log_output.setReadOnly(True)
        self.log_output.setPlaceholderText("Session events appear here.")
        log_layout.addWidget(self.log_output)

        splitter.addWidget(seg_widget)
        splitter.addWidget(log_widget)
        splitter.setSizes([340, 540])
        layout.addWidget(splitter, 1)

        self.statusBar().showMessage("Ready")

    def _connect_signals(self):
        self.start_btn.clicked.connect(self._on_start_clicked)
        self.stop_btn.clicked.connect(self._stop_download)
        self.browse_btn.clicked.connect(self._browse_folder)
        self.open_folder_btn.clicked.connect(self._open_output_folder)
        self.fetch_info_btn.clicked.connect(self._fetch_stream_info)
        self.schedule_check.toggled.connect(self._on_schedule_toggled)
        self.clear_log_btn.clicked.connect(self.log_output.clear)
        self.segment_list.itemDoubleClicked.connect(self._play_segment)
        self.url_input.textChanged.connect(self._on_url_text_changed)
        self.output_input.textChanged.connect(self._refresh_descriptions)
        self.segment_spin.valueChanged.connect(self._refresh_descriptions)
        self.quality_combo.currentTextChanged.connect(self._refresh_descriptions)
        self.retries_spin.valueChanged.connect(self._refresh_descriptions)
        self.schedule_dt.dateTimeChanged.connect(self._refresh_descriptions)

    def _restore_settings(self):
        c = self._config
        if 'output_dir' in c:
            self.output_input.setText(c['output_dir'])
        if 'segment_minutes' in c:
            self.segment_spin.setValue(c['segment_minutes'])
        if 'quality' in c:
            idx = self.quality_combo.findText(c['quality'])
            if idx >= 0:
                self.quality_combo.setCurrentIndex(idx)
        if 'retries' in c:
            self.retries_spin.setValue(c['retries'])
        if 'last_url' in c:
            self.url_input.setText(c['last_url'])

    def _save_settings(self):
        self._config.update({
            'output_dir': self.output_input.text().strip(),
            'segment_minutes': self.segment_spin.value(),
            'quality': self.quality_combo.currentText(),
            'retries': self.retries_spin.value(),
            'last_url': self.url_input.text().strip(),
        })
        save_config(self._config)

    def _set_stream_preview_placeholder(
        self,
        title="No stream preview yet",
        meta="Use Preview stream to confirm the title and current live status before you start recording.",
        hint="If you skip preview, the app still tries to infer the stream title automatically when recording begins.",
        preview_badge=("Awaiting preview", "neutral"),
        live_badge=("Status unknown", "neutral"),
        filename_badge=("Filename auto", "neutral"),
    ):
        self.stream_preview_badge.set_status(*preview_badge)
        self.stream_live_label.set_status(*live_badge)
        self.stream_filename_badge.set_status(*filename_badge)
        self.stream_title_label.setText(title)
        self.stream_meta_label.setText(meta)
        self.stream_hint_label.setText(hint)

    def _refresh_descriptions(self):
        quality = self.quality_combo.currentText()
        retries = self.retries_spin.value()
        segment_minutes = self.segment_spin.value()
        output_dir = self.output_input.text().strip() or self._default_output
        extension = ".m4a" if quality == "Audio Only" else ".mp4"
        quality_phrase = "audio-only" if quality == "Audio Only" else quality

        capture_summary = (
            f"{segment_minutes}-minute {extension} segments in {quality_phrase} quality, with "
            f"{retries} retry{'ies' if retries != 1 else 'y'} per segment."
        )
        self.capture_summary_label.setText(capture_summary)
        self.hero_summary_label.setText(capture_summary)

        if self.schedule_check.isChecked():
            target = self.schedule_dt.dateTime().toPyDateTime()
            schedule_text = f"Scheduled to start on {format_when(target)}."
        else:
            schedule_text = "Starts as soon as you click Start session."
        self.schedule_summary_label.setText(schedule_text)
        self.hero_schedule_label.setText(schedule_text)

        self.output_hint_label.setText(
            f"Segments save to {trim_path(output_dir, 76)}. The folder is created automatically if needed."
        )
        self.hero_output_label.setText(f"Saves to {trim_path(output_dir)}")

        self._refresh_action_availability()
        if not self.worker and not self._schedule_timer.isActive():
            self._refresh_idle_state()

    def _refresh_url_guidance(self):
        url = self.url_input.text().strip()

        if not url:
            self.url_hint_label.setText("Paste a youtube.com or youtu.be livestream link to enable previewing and recording.")
            self.url_input.setProperty("state", "default")
        elif looks_like_youtube_url(url):
            if self._previewed_url and url == self._previewed_url and self._stream_info:
                self.url_hint_label.setText("Preview metadata matches the current URL, so title and live status are in sync.")
            else:
                self.url_hint_label.setText("This looks like a YouTube link. Previewing will confirm the title and live status before you record.")
            self.url_input.setProperty("state", "default")
        else:
            self.url_hint_label.setText(
                "This does not look like a typical YouTube URL. You can still try it, but previewing first is strongly recommended."
            )
            self.url_input.setProperty("state", "warning")

        refresh_style(self.url_input)

    def _refresh_action_availability(self):
        url_present = bool(self.url_input.text().strip())
        preview_busy = self.info_worker is not None and self.info_worker.isRunning()

        self.fetch_info_btn.setEnabled(url_present and not preview_busy and not self._session_locked)
        self.start_btn.setEnabled(url_present and self._ffmpeg_ok and not self._session_locked)
        self.stop_btn.setEnabled(self._session_locked)

        if not self._session_locked:
            self.start_btn.setText("Start session")
            self.stop_btn.setText("Stop session")
        elif self._schedule_timer.isActive() and self.worker is None:
            self.start_btn.setText("Scheduled...")
            self.stop_btn.setText("Cancel schedule")
        else:
            self.start_btn.setText("Recording...")

    def _set_banner_state(self, badge_text, title, detail, tone="neutral"):
        self.readiness_badge.set_status(badge_text, tone)
        self.state_badge.set_status(badge_text, tone)
        self.state_banner.setProperty("tone", tone)
        refresh_style(self.state_banner)
        self.state_title_label.setText(title)
        self.state_detail_label.setText(detail)

    def _set_state_value(self, value, tone):
        self.stat_status.set_value(value)
        self.stat_status.set_tone(tone)

    def _refresh_idle_state(self):
        url = self.url_input.text().strip()
        output_dir = self.output_input.text().strip() or self._default_output

        if not url:
            self._set_banner_state(
                "Idle",
                "Add a livestream URL to begin",
                "Preview it first if you want to confirm the title and live status before the first segment starts.",
                "neutral",
            )
            self._set_state_value("Idle", "neutral")
            return

        if not self._ffmpeg_ok:
            self._set_banner_state(
                "Blocked",
                "Install ffmpeg before starting a session",
                "yt-dlp can be installed automatically, but ffmpeg must already be on your PATH for segmented recording.",
                "warning",
            )
            self._set_state_value("Blocked", "warning")
            return

        if self.schedule_check.isChecked():
            target = self.schedule_dt.dateTime().toPyDateTime()
            if target > datetime.now():
                self._set_banner_state(
                    "Scheduled",
                    "Ready for a scheduled capture",
                    f"The session will arm now and begin on {format_when(target)}. Segments will save into {trim_path(output_dir, 64)}.",
                    "info",
                )
                self._set_state_value("Ready", "info")
                return

        if self._stream_info:
            title = self._stream_info.get('title', 'Untitled stream')
            is_live = self._stream_info.get('is_live', False)
            tone = "success" if is_live else "accent"
            detail = (
                "Preview looks good and YouTube currently reports the stream as live."
                if is_live else
                "Preview is loaded. YouTube did not report the stream as live during the last check."
            )
            self._set_banner_state("Ready", title, detail, tone)
            self._set_state_value("Ready", tone)
            return

        self._set_banner_state(
            "Ready",
            "Ready to record",
            "You can start immediately, or preview the stream first for a cleaner title and stronger confidence before recording.",
            "accent",
        )
        self._set_state_value("Ready", "accent")

    def _sync_segment_state(self):
        has_segments = self.segment_list.count() > 0
        self.segment_empty_label.setVisible(not has_segments)
        self.segment_list.setVisible(has_segments)
        self.segment_count_badge.set_status(
            f"{self.segment_list.count()} saved" if has_segments else "0 saved",
            "success" if has_segments else "neutral",
        )

    def _on_schedule_toggled(self, checked):
        self.schedule_dt.setEnabled(checked and not self._session_locked)
        self._refresh_descriptions()

    def _on_url_text_changed(self):
        current_url = self.url_input.text().strip()
        if self._stream_info and self._previewed_url and current_url != self._previewed_url:
            self._stream_info = None
            self._previewed_url = None
            self._set_stream_preview_placeholder(
                title="Preview needs a refresh",
                meta="The URL changed after the last preview. Preview again to refresh the title, live status, and filename prefix.",
                hint="You can still record immediately, but refreshing keeps the metadata aligned with the URL you pasted.",
                preview_badge=("Preview stale", "warning"),
                live_badge=("Status unknown", "neutral"),
                filename_badge=("Filename auto", "neutral"),
            )
        self._refresh_url_guidance()
        self._refresh_action_availability()
        if not self.worker and not self._schedule_timer.isActive():
            self._refresh_idle_state()

    def _check_deps(self):
        yt_version = check_dependency('yt-dlp')
        ffmpeg_version = check_dependency('ffmpeg')

        self._ytdlp_ok = bool(yt_version)
        self._ffmpeg_ok = bool(ffmpeg_version)

        if yt_version:
            self.dep_ytdlp_label.set_status(f"yt-dlp {yt_version.split()[0]}", "success")
            self.dep_ytdlp_label.setToolTip(yt_version)
        else:
            self.dep_ytdlp_label.set_status("yt-dlp missing", "warning")
            self.dep_ytdlp_label.setToolTip(
                "yt-dlp can usually be auto-installed on startup if Python can install packages."
            )

        if ffmpeg_version:
            self.dep_ffmpeg_label.set_status("ffmpeg ready", "success")
            self.dep_ffmpeg_label.setToolTip(ffmpeg_version)
        else:
            self.dep_ffmpeg_label.set_status("ffmpeg missing", "danger")
            self.dep_ffmpeg_label.setToolTip("Install ffmpeg and make sure it is on PATH before recording.")

        self._refresh_action_availability()
        if not self.worker and not self._schedule_timer.isActive():
            self._refresh_idle_state()

    def _get_ytdlp_cmd(self):
        path = shutil.which('yt-dlp')
        if path:
            return [path]
        return [sys.executable, '-m', 'yt_dlp']

    def _fetch_stream_info(self):
        url = self.url_input.text().strip()
        if not url:
            self.url_input.setFocus()
            return
        self.fetch_info_btn.setEnabled(False)
        self.fetch_info_btn.setText("Checking...")
        self._set_stream_preview_placeholder(
            title="Fetching stream details...",
            meta="Checking the title and live status with yt-dlp. This usually takes a few seconds.",
            hint="If preview fails, you can still try recording directly if the link is valid and live.",
            preview_badge=("Checking", "info"),
            live_badge=("Looking up", "info"),
            filename_badge=("Resolving title", "info"),
        )
        if not self.worker and not self._schedule_timer.isActive():
            self._set_banner_state(
                "Checking",
                "Checking stream availability",
                "Fetching title and live status so the session starts with better context.",
                "info",
            )
            self._set_state_value("Checking", "info")
        self.info_worker = StreamInfoWorker(url, self._get_ytdlp_cmd())
        self.info_worker.info_ready.connect(self._on_stream_info)
        self.info_worker.error.connect(self._on_stream_info_error)
        self.info_worker.finished.connect(self._on_stream_info_finished)
        self.info_worker.start()

    def _on_stream_info_finished(self):
        self.fetch_info_btn.setEnabled(not self._session_locked and bool(self.url_input.text().strip()))
        self.fetch_info_btn.setText("Preview stream")
        self.info_worker = None
        self._refresh_action_availability()
        if not self.worker and not self._schedule_timer.isActive():
            self._refresh_idle_state()

    def _on_stream_info(self, info):
        self._stream_info = info
        self._previewed_url = self.url_input.text().strip()
        title = info.get('title', 'Unknown')
        is_live = info.get('is_live', False)
        safe_title = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', title)
        safe_title = re.sub(r'_+', '_', safe_title)[:80].strip('_ ') or "livestream"
        self.stream_title_label.setText(title)
        self.stream_meta_label.setText(
            "YouTube currently reports this stream as live."
            if is_live else
            "YouTube did not report this stream as live during the last preview."
        )
        self.stream_hint_label.setText(f"Segments will use '{safe_title}' as the filename prefix when possible.")
        self.stream_preview_badge.set_status("Preview ready", "success" if is_live else "accent")
        self.stream_live_label.set_status("Live now" if is_live else "Not live", "success" if is_live else "warning")
        self.stream_filename_badge.set_status("Prefix ready", "accent")
        self._log(f"Preview loaded: {title} ({'live' if is_live else 'not live'})")
        self._refresh_idle_state()

    def _on_stream_info_error(self, msg):
        self._stream_info = None
        self._previewed_url = None
        clean_msg = msg.strip() or "Preview failed."
        self._set_stream_preview_placeholder(
            title="Could not preview this stream",
            meta=clean_msg,
            hint="You can still start a session manually if the link is valid and the stream is live, but previewing again is recommended.",
            preview_badge=("Preview unavailable", "warning"),
            live_badge=("Check log", "warning"),
            filename_badge=("Filename auto", "neutral"),
        )
        self._log(f"Preview error: {clean_msg}")
        if not self.worker and not self._schedule_timer.isActive():
            self._set_banner_state("Preview issue", "Preview could not confirm the stream", clean_msg, "warning")
            self._set_state_value("Ready", "warning")

    def _browse_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Output Folder", self.output_input.text())
        if folder:
            self.output_input.setText(folder)

    def _open_output_folder(self):
        folder = self.output_input.text().strip() or self._default_output
        if not os.path.isdir(folder):
            os.makedirs(folder, exist_ok=True)
        if sys.platform == 'win32':
            os.startfile(folder)
        elif sys.platform == 'darwin':
            subprocess.Popen(['open', folder])
        else:
            subprocess.Popen(['xdg-open', folder])

    def _play_segment(self, item):
        row = self.segment_list.row(item)
        if row < len(self._segment_paths):
            filepath = self._segment_paths[row]
            if os.path.isfile(filepath):
                QDesktopServices.openUrl(QUrl.fromLocalFile(filepath))

    def _log(self, msg):
        timestamp = datetime.now().strftime("%H:%M:%S")
        escaped = html.escape(msg)
        lower = msg.lower()
        if "error" in lower or "failed" in lower:
            color = THEME["danger"]
        elif "retry" in lower or "warning" in lower or "not live" in lower:
            color = THEME["warning"]
        elif "complete" in lower or "saved" in lower or "starting" in lower or "ready" in lower:
            color = THEME["success"]
        else:
            color = "#d7e4f7"

        self.log_output.append(
            f"<span style='color:{THEME['text_muted']};'>[{timestamp}]</span> "
            f"<span style='color:{color};'>{escaped}</span>"
        )
        sb = self.log_output.verticalScrollBar()
        sb.setValue(sb.maximum())

    def _on_start_clicked(self):
        if self.schedule_check.isChecked():
            target = self.schedule_dt.dateTime().toPyDateTime()
            if target > datetime.now():
                self._log(f"Session scheduled for {format_when(target)}")
                self._set_recording_state(True)
                self._set_banner_state(
                    "Scheduled",
                    "Scheduled capture is armed",
                    f"The session will begin on {format_when(target)}. Press Cancel schedule if plans change.",
                    "info",
                )
                self._set_state_value("Scheduled", "info")
                self._schedule_timer.start(1000)
                return
        self._start_download()

    def _check_scheduled_start(self):
        target = self.schedule_dt.dateTime().toPyDateTime()
        remaining = (target - datetime.now()).total_seconds()
        if remaining <= 0:
            self._schedule_timer.stop()
            self._log("Scheduled time reached. Starting session...")
            self._start_download()
        else:
            detail = f"Starting in {format_remaining(remaining)} on {format_when(target)}."
            self._set_banner_state("Scheduled", "Scheduled capture is armed", detail, "info")
            self._set_state_value("Scheduled", "info")
            self.statusBar().showMessage(detail)

    def _start_download(self):
        url = self.url_input.text().strip()
        if not url:
            self.url_input.setFocus()
            self._set_banner_state(
                "Needs URL",
                "Paste a livestream URL before starting",
                "Add a youtube.com or youtu.be livestream link, then preview it or start the session directly.",
                "warning",
            )
            self._set_state_value("Idle", "warning")
            return

        if not shutil.which('ffmpeg'):
            self._check_deps()
            self._set_banner_state(
                "Blocked",
                "ffmpeg is required before recording can start",
                "Install ffmpeg, restart the app, and then try again. yt-dlp alone is not enough for segmented recording.",
                "danger",
            )
            self._set_state_value("Blocked", "danger")
            self._set_recording_state(False)
            self.statusBar().showMessage("ffmpeg not found")
            return

        output_dir = self.output_input.text().strip() or self._default_output
        self.output_input.setText(output_dir)

        self._save_settings()
        self._session_error = False
        self._user_stopped = False
        self._total_bytes = 0
        self._segment_count = 0
        self._segment_paths.clear()
        self.segment_list.clear()
        self._sync_segment_state()
        self.stat_segments.set_value("0")
        self.stat_size.set_value("0 MB")
        self.stat_elapsed.set_value("00:00")

        self._log(f"Starting session: {url}")
        self._set_recording_state(True)
        self._set_banner_state(
            "Recording",
            "Preparing the first segment",
            f"Resolving the stream and writing new files into {trim_path(output_dir, 68)}.",
            "success",
        )
        self._set_state_value("Recording", "success")

        self._recording_start = time.time()
        self._elapsed_timer.start(1000)

        prefix = ""
        if self._stream_info:
            raw = self._stream_info.get('title', '')
            prefix = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', raw)
            prefix = re.sub(r'_+', '_', prefix)[:80].strip('_ ')

        self.worker = SegmentDownloader(
            url=url,
            output_dir=output_dir,
            segment_minutes=self.segment_spin.value(),
            quality=self.quality_combo.currentText(),
            max_retries=self.retries_spin.value(),
            retry_delay=10,
            filename_prefix=prefix,
        )
        self.worker.log_message.connect(self._log)
        self.worker.segment_complete.connect(self._on_segment_complete)
        self.worker.status_update.connect(self._handle_worker_status)
        self.worker.error.connect(self._on_error)
        self.worker.finished_all.connect(self._on_finished)
        self.worker.start()

    def _handle_worker_status(self, msg):
        self.statusBar().showMessage(msg)
        lower = msg.lower()
        if "retry" in lower:
            self._set_banner_state("Retrying", "Recovering the current segment", msg, "warning")
            self._set_state_value("Retrying", "warning")
        else:
            self._set_banner_state("Recording", "Recording in progress", msg, "success")
            self._set_state_value("Recording", "success")

    def _stop_download(self):
        self._schedule_timer.stop()
        if self.worker:
            self._user_stopped = True
            self._log("Stopping after the current segment finalizes...")
            self.stop_btn.setEnabled(False)
            self.stop_btn.setText("Stopping...")
            self._set_banner_state(
                "Stopping",
                "Wrapping up the current segment",
                "The current file will be finalized before the session fully stops.",
                "warning",
            )
            self._set_state_value("Stopping", "warning")
            self.worker.request_stop()
        else:
            if self._session_locked:
                self._log("Scheduled session canceled.")
            self._set_recording_state(False)
            self._refresh_idle_state()

    def _set_recording_state(self, recording):
        self._session_locked = recording
        self.url_input.setEnabled(not recording)
        self.output_input.setEnabled(not recording)
        self.browse_btn.setEnabled(not recording)
        self.segment_spin.setEnabled(not recording)
        self.quality_combo.setEnabled(not recording)
        self.retries_spin.setEnabled(not recording)
        self.schedule_check.setEnabled(not recording)
        self.schedule_dt.setEnabled(not recording and self.schedule_check.isChecked())
        self._refresh_action_availability()

    def _on_segment_complete(self, filepath, size_bytes):
        self._segment_count += 1
        self._total_bytes += size_bytes
        self._segment_paths.append(filepath)

        filename = os.path.basename(filepath)
        size_mb = size_bytes / (1024 * 1024)
        saved_at = datetime.now().strftime("%b %d at %I:%M %p")
        item = QListWidgetItem(f"{filename}  |  {size_mb:.1f} MB  |  Saved {saved_at}")
        self.segment_list.addItem(item)
        self.segment_list.scrollToBottom()
        self._sync_segment_state()

        self.stat_segments.set_value(str(self._segment_count))
        self.stat_size.set_value(human_bytes(self._total_bytes))
        self.segment_count_badge.set_status(f"{self._segment_count} saved", "success")

        ToastNotification(self, f"Segment {self._segment_count} saved: {filename}", "success")

    def _update_elapsed(self):
        if self._recording_start:
            elapsed = time.time() - self._recording_start
            h = int(elapsed // 3600)
            m = int((elapsed % 3600) // 60)
            s = int(elapsed % 60)
            if h > 0:
                self.stat_elapsed.set_value(f"{h}:{m:02d}:{s:02d}")
            else:
                self.stat_elapsed.set_value(f"{m:02d}:{s:02d}")

    def _on_error(self, msg):
        self._session_error = True
        self._log(f"ERROR: {msg}")
        self._elapsed_timer.stop()
        first_line = msg.strip().splitlines()[0] if msg.strip() else "Something went wrong."
        self._set_banner_state("Error", "Session needs attention", first_line, "danger")
        self._set_state_value("Error", "danger")
        self.statusBar().showMessage("Error - review the activity log")

    def _on_finished(self):
        self._set_recording_state(False)
        self._elapsed_timer.stop()
        total_summary = f"{self._segment_count} segment{'s' if self._segment_count != 1 else ''}, {human_bytes(self._total_bytes)} total"
        if self._session_error:
            self._set_banner_state(
                "Error",
                "Session stopped because of an error",
                "Review the activity log for the exact failure, then adjust the setup and try again.",
                "danger",
            )
            self._set_state_value("Error", "danger")
            self.statusBar().showMessage("Error - review the activity log")
        elif self._user_stopped:
            self._set_banner_state(
                "Stopped",
                "Session stopped cleanly",
                f"Capture ended at your request. Saved {total_summary}.",
                "warning",
            )
            self._set_state_value("Stopped", "warning")
            self.statusBar().showMessage(f"Stopped - {total_summary}")
        else:
            self._set_banner_state(
                "Done",
                "Session complete",
                f"Capture finished and saved {total_summary}.",
                "success",
            )
            self._set_state_value("Done", "success")
            self.statusBar().showMessage(f"Done - {total_summary}")
        self._log("Recording session ended.")
        self.worker = None
        self._user_stopped = False

    def closeEvent(self, event):
        self._save_settings()
        if self.worker and self.worker.isRunning():
            self.worker.request_stop()
            self.worker.wait(5000)
        event.accept()


# ──────────────────────────────────────────────
# Entry Point
# ──────────────────────────────────────────────
def main():
    def exception_handler(exc_type, exc_value, exc_tb):
        msg = ''.join(traceback.format_exception(exc_type, exc_value, exc_tb))
        crash_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'crash.log')
        with open(crash_file, 'w') as f:
            f.write(msg)
        print(msg)
        sys.exit(1)
    sys.excepthook = exception_handler

    app = QApplication(sys.argv)

    branding_icon = QIcon(str(_branding_icon_path()))

    app.setWindowIcon(branding_icon)
    app.setStyle("Fusion")
    app.setStyleSheet(DARK_STYLE)

    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor(THEME["bg"]))
    palette.setColor(QPalette.ColorRole.WindowText, QColor(THEME["text"]))
    palette.setColor(QPalette.ColorRole.Base, QColor(THEME["surface_soft"]))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor(THEME["surface"]))
    palette.setColor(QPalette.ColorRole.Text, QColor(THEME["text"]))
    palette.setColor(QPalette.ColorRole.Button, QColor(THEME["surface_raised"]))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor(THEME["text"]))
    palette.setColor(QPalette.ColorRole.Highlight, QColor(THEME["accent"]))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor(THEME["bg"]))
    app.setPalette(palette)

    window = MainWindow()

    window.setWindowIcon(branding_icon)
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
