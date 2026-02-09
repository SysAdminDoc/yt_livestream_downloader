#!/usr/bin/env python3
"""
YouTube Livestream Downloader v1.0.0
Downloads YouTube livestreams in configurable time segments as separate files.
Uses yt-dlp + ffmpeg under the hood.
"""

import sys, os, subprocess, shutil

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
from datetime import datetime, timedelta
from pathlib import Path

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QSpinBox, QTextEdit, QFileDialog,
    QGroupBox, QGridLayout, QComboBox, QListWidget, QListWidgetItem,
    QSplitter, QStatusBar, QFrame, QCheckBox, QDateTimeEdit, QSizePolicy
)
from PyQt6.QtCore import (
    Qt, QThread, pyqtSignal, QTimer, QDateTime, QSize
)
from PyQt6.QtGui import QFont, QColor, QIcon, QPalette, QDesktopServices
from PyQt6.QtCore import QUrl

VERSION = "1.0.0"
APP_NAME = "YT Livestream Downloader"

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


# ──────────────────────────────────────────────
# Dark Theme (Catppuccin Mocha)
# ──────────────────────────────────────────────
DARK_STYLE = """
QMainWindow, QWidget { background-color: #1e1e2e; color: #cdd6f4; }
QGroupBox {
    border: 1px solid #45475a; border-radius: 8px;
    margin-top: 1em; padding-top: 14px; color: #cdd6f4;
    font-weight: bold;
}
QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 6px; }
QPushButton {
    background-color: #89b4fa; color: #1e1e2e; border: none;
    padding: 8px 20px; border-radius: 6px; font-weight: bold; font-size: 13px;
}
QPushButton:hover { background-color: #74c7ec; }
QPushButton:pressed { background-color: #89dceb; }
QPushButton:disabled { background-color: #45475a; color: #6c7086; }
QPushButton#stopBtn { background-color: #f38ba8; color: #1e1e2e; }
QPushButton#stopBtn:hover { background-color: #eba0ac; }
QPushButton#stopBtn:disabled { background-color: #45475a; color: #6c7086; }
QPushButton#greenBtn { background-color: #a6e3a1; color: #1e1e2e; }
QPushButton#greenBtn:hover { background-color: #94e2d5; }
QPushButton#secondaryBtn {
    background-color: #313244; color: #cdd6f4; border: 1px solid #45475a;
}
QPushButton#secondaryBtn:hover { background-color: #45475a; }
QLineEdit, QSpinBox, QDateTimeEdit {
    background-color: #313244; color: #cdd6f4;
    border: 1px solid #45475a; border-radius: 6px; padding: 8px;
    font-size: 13px; selection-background-color: #89b4fa; selection-color: #1e1e2e;
}
QLineEdit:focus, QSpinBox:focus, QDateTimeEdit:focus { border-color: #89b4fa; }
QComboBox {
    background-color: #313244; color: #cdd6f4;
    border: 1px solid #45475a; border-radius: 6px; padding: 8px;
    font-size: 13px;
}
QComboBox::drop-down { border: none; width: 30px; }
QComboBox::down-arrow {
    image: none; border-left: 5px solid transparent;
    border-right: 5px solid transparent; border-top: 6px solid #cdd6f4;
    margin-right: 8px;
}
QComboBox QAbstractItemView {
    background-color: #313244; color: #cdd6f4;
    border: 1px solid #45475a; selection-background-color: #89b4fa;
    selection-color: #1e1e2e; outline: none;
}
QTextEdit {
    background-color: #11111b; color: #a6adc8;
    border: 1px solid #313244; border-radius: 6px; padding: 8px;
    font-family: 'Cascadia Code', 'Consolas', 'Courier New', monospace;
    font-size: 12px;
}
QListWidget {
    background-color: #11111b; color: #cdd6f4;
    border: 1px solid #313244; border-radius: 6px; padding: 4px;
    font-size: 12px; outline: none;
}
QListWidget::item { padding: 6px 8px; border-radius: 4px; }
QListWidget::item:selected { background-color: #313244; color: #89b4fa; }
QListWidget::item:hover { background-color: #181825; }
QLabel { color: #cdd6f4; }
QLabel#titleLabel { font-size: 20px; font-weight: bold; color: #89b4fa; }
QLabel#subtitleLabel { font-size: 12px; color: #6c7086; }
QLabel#sectionLabel { font-size: 13px; color: #a6adc8; }
QLabel#statValue { font-size: 18px; font-weight: bold; color: #89b4fa; }
QLabel#statLabel { font-size: 11px; color: #6c7086; }
QLabel#streamTitle { font-size: 14px; font-weight: bold; color: #cdd6f4; }
QLabel#liveIndicator { font-size: 12px; font-weight: bold; color: #f38ba8; }
QLabel#depOk { color: #a6e3a1; font-size: 12px; }
QLabel#depBad { color: #f38ba8; font-size: 12px; }
QCheckBox { color: #cdd6f4; spacing: 8px; }
QCheckBox::indicator {
    width: 16px; height: 16px; border-radius: 3px;
    border: 1px solid #45475a; background: #313244;
}
QCheckBox::indicator:checked { background: #89b4fa; border-color: #89b4fa; }
QStatusBar { background-color: #181825; color: #6c7086; font-size: 12px; }
QSplitter::handle { background-color: #313244; height: 2px; }
QFrame#separator { background-color: #313244; }
QFrame#statCard {
    background-color: #181825; border: 1px solid #313244; border-radius: 8px;
    padding: 8px;
}
QScrollBar:vertical { background: #11111b; width: 8px; border: none; }
QScrollBar::handle:vertical { background: #45475a; border-radius: 4px; min-height: 30px; }
QScrollBar::handle:vertical:hover { background: #585b70; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
"""


# ──────────────────────────────────────────────
# Toast Notification Widget
# ──────────────────────────────────────────────
class ToastNotification(QLabel):
    """A self-dismissing toast notification."""
    def __init__(self, parent, message, duration_ms=4000):
        super().__init__(message, parent)
        self.setStyleSheet("""
            background-color: #313244; color: #a6e3a1; padding: 10px 18px;
            border-radius: 8px; border: 1px solid #45475a; font-size: 13px;
        """)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.adjustSize()
        px = (parent.width() - self.width()) // 2
        self.move(px, 12)
        self.show()
        self.raise_()
        QTimer.singleShot(duration_ms, self._fade_out)

    def _fade_out(self):
        self.deleteLater()


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
    def __init__(self, label_text, initial_value="0"):
        super().__init__()
        self.setObjectName("statCard")
        self.setFixedHeight(72)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(2)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.value_label = QLabel(initial_value)
        self.value_label.setObjectName("statValue")
        self.value_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.desc_label = QLabel(label_text)
        self.desc_label.setObjectName("statLabel")
        self.desc_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        layout.addWidget(self.value_label)
        layout.addWidget(self.desc_label)

    def set_value(self, val):
        self.value_label.setText(str(val))


# ──────────────────────────────────────────────
# Main Window
# ──────────────────────────────────────────────
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"{APP_NAME} v{VERSION}")
        self.setMinimumSize(900, 780)
        self.resize(1000, 850)
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

        self._config = load_config()
        self._default_output = self._config.get(
            'output_dir', str(Path.home() / "Downloads" / "YT_Livestreams"))

        self._build_ui()
        self._connect_signals()
        self._restore_settings()
        self._check_deps()

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(20, 16, 20, 12)
        layout.setSpacing(10)

        # ── Header ──
        header = QHBoxLayout()
        title_col = QVBoxLayout()
        title = QLabel(APP_NAME)
        title.setObjectName("titleLabel")
        subtitle = QLabel(f"v{VERSION}  -  Record livestreams in timed segments")
        subtitle.setObjectName("subtitleLabel")
        title_col.addWidget(title)
        title_col.addWidget(subtitle)
        header.addLayout(title_col)
        header.addStretch()

        dep_col = QVBoxLayout()
        dep_col.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.dep_ytdlp_label = QLabel("yt-dlp: checking...")
        self.dep_ytdlp_label.setObjectName("depOk")
        self.dep_ffmpeg_label = QLabel("ffmpeg: checking...")
        self.dep_ffmpeg_label.setObjectName("depOk")
        dep_col.addWidget(self.dep_ytdlp_label)
        dep_col.addWidget(self.dep_ffmpeg_label)
        header.addLayout(dep_col)
        layout.addLayout(header)

        sep = QFrame(); sep.setObjectName("separator"); sep.setFixedHeight(1)
        layout.addWidget(sep)

        # ── Stream Info Bar ──
        self.stream_info_frame = QFrame()
        self.stream_info_frame.setStyleSheet(
            "QFrame { background-color: #181825; border: 1px solid #313244; border-radius: 8px; padding: 8px; }")
        si_layout = QHBoxLayout(self.stream_info_frame)
        si_layout.setContentsMargins(12, 8, 12, 8)
        self.stream_title_label = QLabel("")
        self.stream_title_label.setObjectName("streamTitle")
        self.stream_title_label.setWordWrap(True)
        self.stream_live_label = QLabel("")
        self.stream_live_label.setObjectName("liveIndicator")
        si_layout.addWidget(self.stream_title_label, 1)
        si_layout.addWidget(self.stream_live_label)
        self.stream_info_frame.setVisible(False)
        layout.addWidget(self.stream_info_frame)

        # ── Stream Settings ──
        stream_group = QGroupBox("Stream Settings")
        sg = QGridLayout(stream_group)
        sg.setContentsMargins(16, 20, 16, 12)
        sg.setHorizontalSpacing(12)
        sg.setVerticalSpacing(10)

        sg.addWidget(QLabel("Stream URL:"), 0, 0)
        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("https://www.youtube.com/watch?v=... or https://youtu.be/...")
        sg.addWidget(self.url_input, 0, 1, 1, 2)
        self.fetch_info_btn = QPushButton("Fetch Info")
        self.fetch_info_btn.setObjectName("secondaryBtn")
        self.fetch_info_btn.setFixedWidth(100)
        sg.addWidget(self.fetch_info_btn, 0, 3)

        sg.addWidget(QLabel("Output Folder:"), 1, 0)
        self.output_input = QLineEdit(self._default_output)
        sg.addWidget(self.output_input, 1, 1, 1, 2)
        self.browse_btn = QPushButton("Browse")
        self.browse_btn.setObjectName("secondaryBtn")
        self.browse_btn.setFixedWidth(100)
        sg.addWidget(self.browse_btn, 1, 3)

        sg.addWidget(QLabel("Segment Length:"), 2, 0)
        self.segment_spin = QSpinBox()
        self.segment_spin.setRange(1, 360)
        self.segment_spin.setValue(30)
        self.segment_spin.setSuffix(" min")
        self.segment_spin.setFixedWidth(120)
        sg.addWidget(self.segment_spin, 2, 1)

        sg.addWidget(QLabel("Quality:"), 2, 2, Qt.AlignmentFlag.AlignRight)
        self.quality_combo = QComboBox()
        self.quality_combo.addItems(["Best", "1080p", "720p", "480p", "Audio Only"])
        self.quality_combo.setFixedWidth(140)
        sg.addWidget(self.quality_combo, 2, 3)

        sg.addWidget(QLabel("Retries:"), 3, 0)
        self.retries_spin = QSpinBox()
        self.retries_spin.setRange(0, 20)
        self.retries_spin.setValue(3)
        self.retries_spin.setFixedWidth(120)
        self.retries_spin.setToolTip("Max retry attempts per segment on failure")
        sg.addWidget(self.retries_spin, 3, 1)

        self.schedule_check = QCheckBox("Scheduled Start:")
        self.schedule_check.setToolTip("Delay recording until a specific time")
        sg.addWidget(self.schedule_check, 3, 2, Qt.AlignmentFlag.AlignRight)
        self.schedule_dt = QDateTimeEdit(QDateTime.currentDateTime().addSecs(3600))
        self.schedule_dt.setDisplayFormat("yyyy-MM-dd hh:mm")
        self.schedule_dt.setCalendarPopup(True)
        self.schedule_dt.setEnabled(False)
        self.schedule_dt.setFixedWidth(140)
        sg.addWidget(self.schedule_dt, 3, 3)

        sg.setColumnStretch(1, 1)
        layout.addWidget(stream_group)

        # ── Stats Row ──
        stats_layout = QHBoxLayout()
        stats_layout.setSpacing(10)
        self.stat_segments = StatCard("Segments")
        self.stat_size = StatCard("Total Size")
        self.stat_elapsed = StatCard("Elapsed")
        self.stat_status = StatCard("Status", "Idle")
        stats_layout.addWidget(self.stat_segments)
        stats_layout.addWidget(self.stat_size)
        stats_layout.addWidget(self.stat_elapsed)
        stats_layout.addWidget(self.stat_status)
        layout.addLayout(stats_layout)

        # ── Controls ──
        ctrl = QHBoxLayout()
        ctrl.setSpacing(12)

        self.start_btn = QPushButton("  Start Recording  ")
        self.start_btn.setFixedHeight(42)
        self.start_btn.setCursor(Qt.CursorShape.PointingHandCursor)

        self.stop_btn = QPushButton("  Stop  ")
        self.stop_btn.setObjectName("stopBtn")
        self.stop_btn.setFixedHeight(42)
        self.stop_btn.setFixedWidth(120)
        self.stop_btn.setEnabled(False)
        self.stop_btn.setCursor(Qt.CursorShape.PointingHandCursor)

        self.open_folder_btn = QPushButton("Open Folder")
        self.open_folder_btn.setObjectName("greenBtn")
        self.open_folder_btn.setFixedHeight(42)
        self.open_folder_btn.setFixedWidth(130)
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
        seg_label = QLabel("Recorded Segments  (double-click to play)")
        seg_label.setObjectName("sectionLabel")
        seg_layout.addWidget(seg_label)
        self.segment_list = QListWidget()
        self.segment_list.setAlternatingRowColors(True)
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
        self.clear_log_btn = QPushButton("Clear")
        self.clear_log_btn.setObjectName("secondaryBtn")
        self.clear_log_btn.setFixedSize(60, 26)
        log_header.addWidget(self.clear_log_btn)
        log_layout.addLayout(log_header)

        self.log_output = QTextEdit()
        self.log_output.setReadOnly(True)
        log_layout.addWidget(self.log_output)

        splitter.addWidget(seg_widget)
        splitter.addWidget(log_widget)
        splitter.setSizes([300, 560])
        layout.addWidget(splitter, 1)

        self.statusBar().showMessage("Ready")

    def _connect_signals(self):
        self.start_btn.clicked.connect(self._on_start_clicked)
        self.stop_btn.clicked.connect(self._stop_download)
        self.browse_btn.clicked.connect(self._browse_folder)
        self.open_folder_btn.clicked.connect(self._open_output_folder)
        self.fetch_info_btn.clicked.connect(self._fetch_stream_info)
        self.schedule_check.toggled.connect(self.schedule_dt.setEnabled)
        self.clear_log_btn.clicked.connect(self.log_output.clear)
        self.segment_list.itemDoubleClicked.connect(self._play_segment)

    def _restore_settings(self):
        c = self._config
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

    def _check_deps(self):
        for name, label in [('yt-dlp', self.dep_ytdlp_label), ('ffmpeg', self.dep_ffmpeg_label)]:
            ver = check_dependency(name)
            if ver:
                label.setText(f"{name}: {ver[:40]}")
                label.setObjectName("depOk")
            else:
                label.setText(f"{name}: NOT FOUND")
                label.setObjectName("depBad")
            label.setStyleSheet(label.styleSheet())
            label.style().unpolish(label)
            label.style().polish(label)

    def _get_ytdlp_cmd(self):
        path = shutil.which('yt-dlp')
        if path:
            return [path]
        return [sys.executable, '-m', 'yt_dlp']

    def _fetch_stream_info(self):
        url = self.url_input.text().strip()
        if not url:
            return
        self.fetch_info_btn.setEnabled(False)
        self.fetch_info_btn.setText("...")
        self.info_worker = StreamInfoWorker(url, self._get_ytdlp_cmd())
        self.info_worker.info_ready.connect(self._on_stream_info)
        self.info_worker.error.connect(self._on_stream_info_error)
        self.info_worker.finished.connect(lambda: (
            self.fetch_info_btn.setEnabled(True),
            self.fetch_info_btn.setText("Fetch Info")
        ))
        self.info_worker.start()

    def _on_stream_info(self, info):
        self._stream_info = info
        title = info.get('title', 'Unknown')
        is_live = info.get('is_live', False)
        self.stream_title_label.setText(title)
        self.stream_live_label.setText("LIVE" if is_live else "NOT LIVE")
        if is_live:
            self.stream_live_label.setStyleSheet("color: #f38ba8; font-weight: bold;")
        else:
            self.stream_live_label.setStyleSheet("color: #fab387; font-weight: bold;")
        self.stream_info_frame.setVisible(True)
        self._log(f"Stream: {title} ({'LIVE' if is_live else 'not live'})")

    def _on_stream_info_error(self, msg):
        self._log(f"Stream info error: {msg}")
        self.stream_info_frame.setVisible(False)

    def _browse_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Output Folder", self.output_input.text())
        if folder:
            self.output_input.setText(folder)

    def _open_output_folder(self):
        folder = self.output_input.text()
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
        self.log_output.append(f"[{timestamp}] {msg}")
        sb = self.log_output.verticalScrollBar()
        sb.setValue(sb.maximum())

    def _on_start_clicked(self):
        if self.schedule_check.isChecked():
            target = self.schedule_dt.dateTime().toPyDateTime()
            if target > datetime.now():
                self._log(f"Scheduled to start at {target.strftime('%Y-%m-%d %H:%M')}")
                self.stat_status.set_value("Waiting")
                self._set_recording_state(True)
                self._schedule_timer.start(1000)
                return
        self._start_download()

    def _check_scheduled_start(self):
        target = self.schedule_dt.dateTime().toPyDateTime()
        remaining = (target - datetime.now()).total_seconds()
        if remaining <= 0:
            self._schedule_timer.stop()
            self._log("Scheduled time reached. Starting...")
            self._start_download()
        else:
            mins = int(remaining // 60)
            secs = int(remaining % 60)
            self.stat_status.set_value(f"T-{mins}:{secs:02d}")

    def _start_download(self):
        url = self.url_input.text().strip()
        if not url:
            self._log("Enter a YouTube URL first.")
            return

        if not shutil.which('ffmpeg'):
            self._log("ERROR: ffmpeg not found on PATH. Install ffmpeg first.")
            self._set_recording_state(False)
            return

        output_dir = self.output_input.text().strip() or self._default_output
        self.output_input.setText(output_dir)

        self._save_settings()
        self._total_bytes = 0
        self._segment_count = 0
        self._segment_paths.clear()
        self.segment_list.clear()
        self.stat_segments.set_value("0")
        self.stat_size.set_value("0 MB")
        self.stat_elapsed.set_value("00:00")

        self._log(f"Starting: {url}")
        self._set_recording_state(True)
        self.stat_status.set_value("Recording")

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
        self.worker.status_update.connect(self.statusBar().showMessage)
        self.worker.error.connect(self._on_error)
        self.worker.finished_all.connect(self._on_finished)
        self.worker.start()

    def _stop_download(self):
        self._schedule_timer.stop()
        if self.worker:
            self._log("Stopping (finishing current data)...")
            self.stop_btn.setEnabled(False)
            self.worker.request_stop()
        else:
            self._set_recording_state(False)
            self.stat_status.set_value("Idle")

    def _set_recording_state(self, recording):
        self.start_btn.setEnabled(not recording)
        self.stop_btn.setEnabled(recording)
        self.url_input.setEnabled(not recording)
        self.segment_spin.setEnabled(not recording)
        self.quality_combo.setEnabled(not recording)
        self.retries_spin.setEnabled(not recording)
        self.schedule_check.setEnabled(not recording)
        self.schedule_dt.setEnabled(not recording and self.schedule_check.isChecked())
        self.start_btn.setText("  Recording...  " if recording else "  Start Recording  ")

    def _on_segment_complete(self, filepath, size_bytes):
        self._segment_count += 1
        self._total_bytes += size_bytes
        self._segment_paths.append(filepath)

        filename = os.path.basename(filepath)
        size_mb = size_bytes / (1024 * 1024)
        item = QListWidgetItem(f"  {filename}  ({size_mb:.1f} MB)")
        self.segment_list.addItem(item)
        self.segment_list.scrollToBottom()

        self.stat_segments.set_value(str(self._segment_count))
        total_mb = self._total_bytes / (1024 * 1024)
        if total_mb >= 1024:
            self.stat_size.set_value(f"{total_mb / 1024:.1f} GB")
        else:
            self.stat_size.set_value(f"{total_mb:.0f} MB")

        ToastNotification(self, f"Segment {self._segment_count} saved ({size_mb:.1f} MB)")

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
        self._log(f"ERROR: {msg}")
        self._set_recording_state(False)
        self._elapsed_timer.stop()
        self.stat_status.set_value("Error")
        self.statusBar().showMessage("Error - see log")

    def _on_finished(self):
        self._set_recording_state(False)
        self._elapsed_timer.stop()
        self.stat_status.set_value("Done")
        self.statusBar().showMessage(
            f"Done - {self._segment_count} segments, "
            f"{self._total_bytes / (1024 * 1024):.1f} MB total")
        self._log("Recording session ended.")
        self.worker = None

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
    import traceback as tb
    def exception_handler(exc_type, exc_value, exc_tb):
        msg = ''.join(tb.format_exception(exc_type, exc_value, exc_tb))
        crash_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'crash.log')
        with open(crash_file, 'w') as f:
            f.write(msg)
        print(msg)
        sys.exit(1)
    sys.excepthook = exception_handler

    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setStyleSheet(DARK_STYLE)

    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor("#1e1e2e"))
    palette.setColor(QPalette.ColorRole.WindowText, QColor("#cdd6f4"))
    palette.setColor(QPalette.ColorRole.Base, QColor("#11111b"))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor("#181825"))
    palette.setColor(QPalette.ColorRole.Text, QColor("#cdd6f4"))
    palette.setColor(QPalette.ColorRole.Button, QColor("#313244"))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor("#cdd6f4"))
    palette.setColor(QPalette.ColorRole.Highlight, QColor("#89b4fa"))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor("#1e1e2e"))
    app.setPalette(palette)

    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
