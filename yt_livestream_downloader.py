#!/usr/bin/env python3
"""
YouTube Livestream Downloader v0.2.0
Downloads YouTube livestreams in configurable time increments as separate files.
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

import json, time, signal, re
from datetime import datetime, timedelta
from pathlib import Path

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QSpinBox, QTextEdit, QFileDialog,
    QGroupBox, QGridLayout, QComboBox, QListWidget, QListWidgetItem,
    QSplitter, QStatusBar, QFrame
)
from PyQt6.QtCore import (
    Qt, QThread, pyqtSignal, QTimer, QSize
)
from PyQt6.QtGui import QFont, QColor, QIcon, QPalette

VERSION = "0.2.0"

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
QPushButton#stopBtn {
    background-color: #f38ba8; color: #1e1e2e;
}
QPushButton#stopBtn:hover { background-color: #eba0ac; }
QPushButton#stopBtn:disabled { background-color: #45475a; color: #6c7086; }
QLineEdit, QSpinBox {
    background-color: #313244; color: #cdd6f4;
    border: 1px solid #45475a; border-radius: 6px; padding: 8px;
    font-size: 13px; selection-background-color: #89b4fa; selection-color: #1e1e2e;
}
QLineEdit:focus, QSpinBox:focus { border-color: #89b4fa; }
QComboBox {
    background-color: #313244; color: #cdd6f4;
    border: 1px solid #45475a; border-radius: 6px; padding: 8px;
    font-size: 13px;
}
QComboBox::drop-down { border: none; width: 30px; }
QComboBox::down-arrow { image: none; border-left: 5px solid transparent;
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
QListWidget::item {
    padding: 6px 8px; border-radius: 4px;
}
QListWidget::item:selected {
    background-color: #313244; color: #89b4fa;
}
QListWidget::item:hover {
    background-color: #181825;
}
QLabel { color: #cdd6f4; }
QLabel#titleLabel { font-size: 20px; font-weight: bold; color: #89b4fa; }
QLabel#subtitleLabel { font-size: 12px; color: #6c7086; }
QLabel#sectionLabel { font-size: 13px; color: #a6adc8; }
QStatusBar { background-color: #181825; color: #6c7086; font-size: 12px; }
QSplitter::handle { background-color: #313244; height: 2px; }
QFrame#separator { background-color: #313244; }
QScrollBar:vertical {
    background: #11111b; width: 8px; border: none;
}
QScrollBar::handle:vertical {
    background: #45475a; border-radius: 4px; min-height: 30px;
}
QScrollBar::handle:vertical:hover { background: #585b70; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
"""


# ──────────────────────────────────────────────
# Download Worker Thread
# ──────────────────────────────────────────────
class SegmentDownloader(QThread):
    """Downloads a livestream in timed segments using yt-dlp."""
    log_message = pyqtSignal(str)
    segment_complete = pyqtSignal(str)  # filepath
    status_update = pyqtSignal(str)
    error = pyqtSignal(str)
    finished_all = pyqtSignal()

    def __init__(self, url, output_dir, segment_minutes, quality, parent=None):
        super().__init__(parent)
        self.url = url
        self.output_dir = output_dir
        self.segment_minutes = segment_minutes
        self.quality = quality
        self._stop_requested = False
        self._current_process = None

    def request_stop(self):
        self._stop_requested = True
        if self._current_process:
            try:
                self._current_process.terminate()
            except Exception:
                pass

    def _find_tool(self, name):
        """Find yt-dlp or ffmpeg executable."""
        path = shutil.which(name)
        if path:
            return path
        # Check common locations on Windows
        if sys.platform == 'win32':
            for d in [os.path.dirname(os.path.abspath(__file__)),
                      os.path.expanduser('~'), os.path.join(os.environ.get('LOCALAPPDATA', ''), 'Programs')]:
                for ext in ['.exe', '']:
                    candidate = os.path.join(d, f"{name}{ext}")
                    if os.path.isfile(candidate):
                        return candidate
        # Try the pip-installed yt-dlp module
        if name == 'yt-dlp':
            return [sys.executable, '-m', 'yt_dlp']
        return None

    def _get_ytdlp_cmd(self):
        """Return yt-dlp command as list."""
        path = self._find_tool('yt-dlp')
        if path and isinstance(path, list):
            return path
        if path:
            return [path]
        return [sys.executable, '-m', 'yt_dlp']

    def _check_ffmpeg(self):
        """Verify ffmpeg is available."""
        return shutil.which('ffmpeg') is not None

    def run(self):
        try:
            if not self._check_ffmpeg():
                self.error.emit("ffmpeg not found in PATH. Please install ffmpeg and ensure it's on your system PATH.")
                return

            ytdlp_cmd = self._get_ytdlp_cmd()
            self.log_message.emit(f"Using yt-dlp: {' '.join(ytdlp_cmd)}")
            self.log_message.emit(f"Output directory: {self.output_dir}")
            self.log_message.emit(f"Segment duration: {self.segment_minutes} minutes")

            # Verify the URL is a valid livestream
            self.status_update.emit("Checking stream...")
            self.log_message.emit("Fetching stream info...")

            info_cmd = ytdlp_cmd + [
                '--dump-json', '--no-download', self.url
            ]
            try:
                result = subprocess.run(info_cmd, capture_output=True, text=True, timeout=30)
                if result.returncode != 0:
                    stderr = result.stderr.strip()
                    if 'is not a valid URL' in stderr or 'Unsupported URL' in stderr:
                        self.error.emit(f"Invalid URL: {self.url}")
                        return
                    self.log_message.emit(f"Warning: {stderr}")

                if result.stdout.strip():
                    info = json.loads(result.stdout.strip().split('\n')[0])
                    title = info.get('title', 'Unknown')
                    is_live = info.get('is_live', False)
                    self.log_message.emit(f"Stream title: {title}")
                    if is_live:
                        self.log_message.emit("Confirmed: Stream is LIVE")
                    else:
                        self.log_message.emit("Note: Stream may not be live (will attempt download anyway)")
                    # Sanitize title for filename
                    safe_title = re.sub(r'[<>:"/\\|?*]', '_', title)[:60].strip('_ ')
                else:
                    safe_title = "livestream"
            except subprocess.TimeoutExpired:
                self.log_message.emit("Info fetch timed out, proceeding anyway...")
                safe_title = "livestream"
            except (json.JSONDecodeError, KeyError):
                safe_title = "livestream"

            os.makedirs(self.output_dir, exist_ok=True)
            segment_num = 1
            segment_secs = self.segment_minutes * 60

            # Quality format selection — use 'b' not 'best' to suppress yt-dlp warning
            # For livestreams, merged format strings with + often fail, so use fallback chains
            format_map = {
                "Best": None,  # Let yt-dlp auto-select (best for livestreams)
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
                self.log_message.emit(f"\n--- Segment {segment_num} started at {datetime.now().strftime('%H:%M:%S')} ---")
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

                self.log_message.emit(f"Command: {' '.join(cmd)}")

                try:
                    self._current_process = subprocess.Popen(
                        cmd,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.STDOUT,
                        text=True,
                        bufsize=1,
                        creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0
                    )

                    start_time = time.time()
                    for line in iter(self._current_process.stdout.readline, ''):
                        if self._stop_requested:
                            break
                        line = line.strip()
                        if line:
                            # Filter to meaningful output
                            if any(k in line.lower() for k in ['download', 'error', 'warning', 'merge', 'frame', 'size', '%']):
                                self.log_message.emit(line)
                            elapsed = time.time() - start_time
                            mins = int(elapsed // 60)
                            secs = int(elapsed % 60)
                            self.status_update.emit(
                                f"Recording segment {segment_num} - {mins:02d}:{secs:02d} / {self.segment_minutes:02d}:00"
                            )

                    self._current_process.wait(timeout=10)

                except subprocess.TimeoutExpired:
                    self._current_process.kill()
                except Exception as e:
                    self.log_message.emit(f"Process error: {e}")

                self._current_process = None

                if self._stop_requested:
                    self.log_message.emit("\nDownload stopped by user.")
                    if os.path.isfile(filepath) and os.path.getsize(filepath) > 0:
                        self.log_message.emit(f"Partial segment saved: {filename}")
                        self.segment_complete.emit(filepath)
                    break

                # Check if file was created and has content
                if os.path.isfile(filepath) and os.path.getsize(filepath) > 0:
                    size_mb = os.path.getsize(filepath) / (1024 * 1024)
                    self.log_message.emit(f"Segment {segment_num} complete: {size_mb:.1f} MB")
                    self.segment_complete.emit(filepath)
                    segment_num += 1
                else:
                    self.log_message.emit("Segment file empty or missing. Stream may have ended.")
                    # Clean up empty file
                    if os.path.isfile(filepath):
                        os.remove(filepath)
                    break

            self.finished_all.emit()

        except Exception as e:
            self.error.emit(str(e))
            self.finished_all.emit()


# ──────────────────────────────────────────────
# Main Window
# ──────────────────────────────────────────────
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"YT Livestream Downloader v{VERSION}")
        self.setMinimumSize(850, 700)
        self.resize(950, 780)
        self.worker = None

        self._default_output = str(Path.home() / "Downloads" / "YT_Livestreams")

        self._build_ui()
        self._connect_signals()

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(20, 16, 20, 12)
        layout.setSpacing(12)

        # ── Title ──
        title = QLabel("YT Livestream Downloader")
        title.setObjectName("titleLabel")
        subtitle = QLabel(f"v{VERSION}  -  Record livestreams in timed segments")
        subtitle.setObjectName("subtitleLabel")
        layout.addWidget(title)
        layout.addWidget(subtitle)

        sep = QFrame()
        sep.setObjectName("separator")
        sep.setFixedHeight(1)
        layout.addWidget(sep)

        # ── Stream Settings Group ──
        stream_group = QGroupBox("Stream Settings")
        sg_layout = QGridLayout(stream_group)
        sg_layout.setContentsMargins(16, 20, 16, 12)
        sg_layout.setHorizontalSpacing(12)
        sg_layout.setVerticalSpacing(10)

        sg_layout.addWidget(QLabel("Stream URL:"), 0, 0)
        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("https://www.youtube.com/watch?v=... or https://youtu.be/...")
        sg_layout.addWidget(self.url_input, 0, 1, 1, 3)

        sg_layout.addWidget(QLabel("Output Folder:"), 1, 0)
        self.output_input = QLineEdit(self._default_output)
        sg_layout.addWidget(self.output_input, 1, 1, 1, 2)
        self.browse_btn = QPushButton("Browse")
        self.browse_btn.setFixedWidth(90)
        sg_layout.addWidget(self.browse_btn, 1, 3)

        sg_layout.addWidget(QLabel("Segment Length:"), 2, 0)
        self.segment_spin = QSpinBox()
        self.segment_spin.setRange(1, 360)
        self.segment_spin.setValue(30)
        self.segment_spin.setSuffix(" min")
        self.segment_spin.setFixedWidth(120)
        sg_layout.addWidget(self.segment_spin, 2, 1)

        sg_layout.addWidget(QLabel("Quality:"), 2, 2, Qt.AlignmentFlag.AlignRight)
        self.quality_combo = QComboBox()
        self.quality_combo.addItems(["Best", "1080p", "720p", "480p", "Audio Only"])
        self.quality_combo.setFixedWidth(140)
        sg_layout.addWidget(self.quality_combo, 2, 3)

        sg_layout.setColumnStretch(1, 1)
        layout.addWidget(stream_group)

        # ── Controls ──
        ctrl_layout = QHBoxLayout()
        ctrl_layout.setSpacing(12)

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
        self.open_folder_btn.setFixedHeight(42)
        self.open_folder_btn.setFixedWidth(120)
        self.open_folder_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.open_folder_btn.setStyleSheet(
            "QPushButton { background-color: #a6e3a1; color: #1e1e2e; }"
            "QPushButton:hover { background-color: #94e2d5; }"
        )

        ctrl_layout.addWidget(self.start_btn)
        ctrl_layout.addWidget(self.stop_btn)
        ctrl_layout.addStretch()
        ctrl_layout.addWidget(self.open_folder_btn)
        layout.addLayout(ctrl_layout)

        # ── Splitter: Segments + Log ──
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Segments list
        seg_widget = QWidget()
        seg_layout = QVBoxLayout(seg_widget)
        seg_layout.setContentsMargins(0, 0, 0, 0)
        seg_layout.setSpacing(6)
        seg_label = QLabel("Recorded Segments")
        seg_label.setObjectName("sectionLabel")
        seg_layout.addWidget(seg_label)
        self.segment_list = QListWidget()
        self.segment_list.setAlternatingRowColors(True)
        seg_layout.addWidget(self.segment_list)

        # Log output
        log_widget = QWidget()
        log_layout = QVBoxLayout(log_widget)
        log_layout.setContentsMargins(0, 0, 0, 0)
        log_layout.setSpacing(6)
        log_label = QLabel("Activity Log")
        log_label.setObjectName("sectionLabel")
        log_layout.addWidget(log_label)
        self.log_output = QTextEdit()
        self.log_output.setReadOnly(True)
        log_layout.addWidget(self.log_output)

        splitter.addWidget(seg_widget)
        splitter.addWidget(log_widget)
        splitter.setSizes([280, 520])
        layout.addWidget(splitter, 1)

        # ── Status Bar ──
        self.statusBar().showMessage("Ready")

    def _connect_signals(self):
        self.start_btn.clicked.connect(self._start_download)
        self.stop_btn.clicked.connect(self._stop_download)
        self.browse_btn.clicked.connect(self._browse_folder)
        self.open_folder_btn.clicked.connect(self._open_output_folder)

    def _browse_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Output Folder", self.output_input.text())
        if folder:
            self.output_input.setText(folder)

    def _open_output_folder(self):
        folder = self.output_input.text()
        if os.path.isdir(folder):
            if sys.platform == 'win32':
                os.startfile(folder)
            elif sys.platform == 'darwin':
                subprocess.Popen(['open', folder])
            else:
                subprocess.Popen(['xdg-open', folder])
        else:
            self._log("Output folder does not exist yet.")

    def _log(self, msg):
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_output.append(f"[{timestamp}] {msg}")
        # Auto-scroll
        scrollbar = self.log_output.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def _start_download(self):
        url = self.url_input.text().strip()
        if not url:
            self._log("Please enter a YouTube URL.")
            return

        output_dir = self.output_input.text().strip()
        if not output_dir:
            output_dir = self._default_output
            self.output_input.setText(output_dir)

        segment_mins = self.segment_spin.value()
        quality = self.quality_combo.currentText()

        self._log(f"Starting download: {url}")
        self._set_recording_state(True)

        self.worker = SegmentDownloader(url, output_dir, segment_mins, quality)
        self.worker.log_message.connect(self._log)
        self.worker.segment_complete.connect(self._on_segment_complete)
        self.worker.status_update.connect(self.statusBar().showMessage)
        self.worker.error.connect(self._on_error)
        self.worker.finished_all.connect(self._on_finished)
        self.worker.start()

    def _stop_download(self):
        if self.worker:
            self._log("Stopping download (finishing current data)...")
            self.stop_btn.setEnabled(False)
            self.worker.request_stop()

    def _set_recording_state(self, recording):
        self.start_btn.setEnabled(not recording)
        self.stop_btn.setEnabled(recording)
        self.url_input.setEnabled(not recording)
        self.segment_spin.setEnabled(not recording)
        self.quality_combo.setEnabled(not recording)
        if recording:
            self.start_btn.setText("  Recording...  ")
        else:
            self.start_btn.setText("  Start Recording  ")

    def _on_segment_complete(self, filepath):
        filename = os.path.basename(filepath)
        size_mb = os.path.getsize(filepath) / (1024 * 1024)
        item = QListWidgetItem(f"  {filename}  ({size_mb:.1f} MB)")
        self.segment_list.addItem(item)
        self.segment_list.scrollToBottom()

    def _on_error(self, msg):
        self._log(f"ERROR: {msg}")
        self._set_recording_state(False)
        self.statusBar().showMessage("Error - see log")

    def _on_finished(self):
        self._set_recording_state(False)
        self.statusBar().showMessage("Recording complete")
        self._log("Recording session ended.")
        self.worker = None

    def closeEvent(self, event):
        if self.worker and self.worker.isRunning():
            self.worker.request_stop()
            self.worker.wait(5000)
        event.accept()


# ──────────────────────────────────────────────
# Entry Point
# ──────────────────────────────────────────────
def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setStyleSheet(DARK_STYLE)

    # Set dark palette as base
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
