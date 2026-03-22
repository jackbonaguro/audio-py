"""
PySide6 GUI showing stream progress: FFmpeg decode position vs output write position.
"""

import signal
import sys
from pathlib import Path

import numpy as np
from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QPainter, QColor, QPen
from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QProgressBar,
    QSlider,
    QLabel,
    QPushButton,
    QFileDialog,
    QLineEdit,
)

try:
    from .controller import PlaybackController
    from .player import get_duration, passthrough, halftime
    from .utils import bytes_to_seconds, format_time, ratio_to_chunk_index, UI_POLL_MS, SLIDER_RANGE, SEEK_DELAY_MS
except ImportError:
    from controller import PlaybackController
    from player import get_duration, passthrough, halftime
    from utils import bytes_to_seconds, format_time, ratio_to_chunk_index, UI_POLL_MS, SLIDER_RANGE, SEEK_DELAY_MS


def _chunks_to_waveform(chunks: list[bytes], channels: int, width: int) -> np.ndarray:
    """Downsample PCM chunks to min/max per pixel for waveform display. Returns (width, 2) array of [min, max]."""
    if not chunks or channels <= 0:
        return np.zeros((width, 2))
    raw = b"".join(chunks)
    samples = np.frombuffer(raw, dtype=np.int16)
    frames = np.reshape(samples, (-1, channels))
    mono = frames.mean(axis=1).astype(np.float32) / 32768.0
    n = len(mono)
    if n == 0:
        return np.zeros((width, 2))
    samples_per_pixel = max(1, n // width)
    mins = np.zeros(width)
    maxs = np.zeros(width)
    for i in range(width):
        start = i * samples_per_pixel
        end = min((i + 1) * samples_per_pixel, n)
        if start < end:
            mins[i] = mono[start:end].min()
            maxs[i] = mono[start:end].max()
    return np.column_stack((mins, maxs))


class WaveformWidget(QWidget):
    """Paints a waveform from preloaded PCM chunks."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(80)
        self.setStyleSheet("background-color: #1a1a1a; border-radius: 4px;")
        self._chunks: list[bytes] | None = None
        self._channels = 0
        self._waveform: np.ndarray | None = None

    def set_audio(self, chunks: list[bytes], sample_rate: int, channels: int):
        self._chunks = chunks if chunks and channels > 0 else None
        self._channels = channels
        self._recompute_waveform()

    def _recompute_waveform(self):
        w = self.width() or 400
        if self._chunks and w > 0:
            self._waveform = _chunks_to_waveform(self._chunks, self._channels, w)
        else:
            self._waveform = None
        self.update()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._chunks:
            self._recompute_waveform()

    def paintEvent(self, event):
        super().paintEvent(event)
        if self._waveform is None or len(self._waveform) == 0:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        h, w = self.height(), self.width()
        mid, amp = h / 2, (h / 2) * 0.95
        pen = QPen(QColor(100, 180, 255))
        pen.setWidth(1)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        for x in range(min(w, len(self._waveform))):
            mn, mx = self._waveform[x]
            painter.drawLine(int(x), int(mid - mx * amp), int(x), int(mid - mn * amp))


class StreamProgressWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Stream Progress")
        self.setMinimumWidth(400)

        self.controller = PlaybackController(self)
        self.duration_sec = 0.0
        self.file_duration = 0.0
        self.halftime_enabled = False
        self._reload_preserve: tuple[float, bool] | None = None
        self._slider_dragging = False
        self._just_restored_paused = False  # Skip _update_bars overwriting position

        layout = QVBoxLayout()
        layout.setSpacing(12)

        file_layout = QHBoxLayout()
        self.file_edit = QLineEdit()
        _default = Path(__file__).resolve().parent / "gravity.mp3"
        self.file_edit.setText(str(_default) if _default.exists() else "")
        self.file_edit.setPlaceholderText("Select an audio file...")
        self.file_edit.setReadOnly(True)
        browse_btn = QPushButton("Browse")
        browse_btn.clicked.connect(self._browse)
        file_layout.addWidget(self.file_edit, 1)
        file_layout.addWidget(browse_btn)
        layout.addLayout(file_layout)

        btn_layout = QHBoxLayout()
        self.load_btn = QPushButton("Load")
        self.load_btn.clicked.connect(self._load)
        self.play_pause_btn = QPushButton("Play")
        self.halftime_btn = QPushButton("Halftime")
        self.halftime_btn.setCheckable(True)
        self.halftime_btn.clicked.connect(self._toggle_halftime)
        self.play_pause_btn.clicked.connect(self._toggle_play_pause)
        self.play_pause_btn.setEnabled(False)
        btn_layout.addWidget(self.load_btn)
        btn_layout.addWidget(self.play_pause_btn)
        btn_layout.addWidget(self.halftime_btn)
        layout.addLayout(btn_layout)

        layout.addWidget(QLabel("FFmpeg decode (streamed in):"))
        self.decode_bar = QProgressBar()
        self.decode_bar.setRange(0, SLIDER_RANGE)
        self.decode_bar.setValue(0)
        self.decode_label = QLabel("0:00 / 0:00")
        layout.addWidget(self.decode_bar)
        layout.addWidget(self.decode_label)

        layout.addWidget(QLabel("Position:"))
        self.position_slider = QSlider(Qt.Orientation.Horizontal)
        self.position_slider.setRange(0, SLIDER_RANGE)
        self.position_slider.sliderPressed.connect(self._on_slider_pressed)
        self.position_slider.sliderReleased.connect(self._on_slider_released)
        self.position_slider.sliderMoved.connect(self._on_slider_moved)
        layout.addWidget(self.position_slider)
        self.position_label = QLabel("0:00 / 0:00")
        layout.addWidget(self.position_label)

        layout.addWidget(QLabel("Waveform:"))
        self.waveform = WaveformWidget()
        layout.addWidget(self.waveform)

        central = QWidget()
        central.setLayout(layout)
        self.setCentralWidget(central)

        self.update_timer = QTimer(self)
        self.update_timer.timeout.connect(self._update_bars)

        self.controller.load_complete.connect(self._on_load_complete)
        self.controller.load_error.connect(self._on_load_error)
        self.controller.load_finished.connect(self._on_load_finished)
        self.controller.playback_finished.connect(self._on_playback_finished)
        self.controller.playback_error.connect(self._on_playback_error)

    def closeEvent(self, event):
        self.controller.abort()
        self.update_timer.stop()
        event.accept()

    def _shutdown(self):
        self.close()

    def _toggle_halftime(self):
        self.halftime_enabled = self.halftime_btn.isChecked()
        self.halftime_btn.setText("Halftime" if self.halftime_enabled else "Normal")
        path = self.file_edit.text().strip()
        if not path or not Path(path).exists() or self.controller.is_loading():
            return
        c = self.controller
        if c.loaded_chunks:
            total = sum(len(chunk) for chunk in c.loaded_chunks)
            ratio = c.progress.bytes_written / total if total else 0
            was_playing = c.is_playing() and not c.progress.paused
            self._reload_preserve = (max(0, min(1, ratio)), was_playing)
        else:
            self._reload_preserve = None
        self._start_load(Path(path), preserve=self._reload_preserve is not None)

    def _browse(self):
        current = self.file_edit.text().strip()
        start_dir = str(Path(__file__).resolve().parent)
        if current:
            start_path = Path(current)
            start_dir = str(start_path.parent if start_path.is_file() else start_path)
        path, _ = QFileDialog.getOpenFileName(
            self, "Select audio file", start_dir,
            "Audio (*.mp3 *.wav *.flac *.m4a *.ogg);;All files (*)"
        )
        if path:
            self.file_edit.setText(path)

    def _load(self):
        path = Path(self.file_edit.text().strip())
        if not path.exists():
            return
        self._reload_preserve = None
        self._start_load(path)

    def _start_load(self, path: Path, preserve: bool = False):
        if self.controller.is_loading():
            return
        if not preserve:
            self._reload_preserve = None
        self.file_duration = get_duration(path)
        self.duration_sec = self.file_duration * 2 if self.halftime_enabled else self.file_duration
        if preserve and self._reload_preserve:
            ratio, _ = self._reload_preserve
            self.position_slider.setValue(int(ratio * SLIDER_RANGE))
            self.position_label.setText(f"{format_time(ratio * self.duration_sec)} / {format_time(self.duration_sec)}")
        if not preserve:
            self.waveform.set_audio([], 0, 0)
        transform = halftime if self.halftime_enabled else passthrough
        if self.controller.load(path, transform):
            self.load_btn.setEnabled(False)
            self.play_pause_btn.setEnabled(False)
            if preserve:
                self.halftime_btn.setEnabled(False)
            self.update_timer.start(UI_POLL_MS)

    def _on_load_complete(self, chunks: list[bytes], sample_rate: int, channels: int):
        self.waveform.set_audio(chunks, sample_rate, channels)
        self.play_pause_btn.setEnabled(True)
        self.play_pause_btn.setText("Play")
        p = self.controller.progress
        p.sample_rate = sample_rate
        p.channels = channels
        if self._reload_preserve is not None:
            ratio, was_playing = self._reload_preserve
            if chunks:
                chunk_index = ratio_to_chunk_index(chunks, ratio)
                p.bytes_written = sum(len(c) for c in chunks[:chunk_index])
                p.seek_to_chunk = chunk_index
                self.position_slider.setValue(int(ratio * SLIDER_RANGE))
                if was_playing:
                    self.controller.start_playback(restore_ratio=ratio, restore_was_playing=True)
                    self.play_pause_btn.setText("Pause")
                    self.update_timer.start(UI_POLL_MS)
                else:
                    self._just_restored_paused = True  # Don't let _update_bars overwrite
            self._reload_preserve = None

    def _on_load_finished(self):
        self.load_btn.setEnabled(True)
        self.halftime_btn.setEnabled(True)
        if not self.controller.is_playing():
            self.update_timer.stop()
        if self._just_restored_paused:
            self._just_restored_paused = False
            # Position already set in _on_load_complete; only update decode bar
            p = self.controller.progress
            decode_sec = bytes_to_seconds(p.bytes_decoded, p.sample_rate, p.channels) if (p.sample_rate and p.channels) else 0.0
            self.decode_bar.setValue(SLIDER_RANGE)  # 100%
            self.decode_label.setText(f"{format_time(decode_sec)} / {format_time(self.file_duration)}")
            output_sec = bytes_to_seconds(p.bytes_written, p.sample_rate, p.channels) if (p.sample_rate and p.channels) else 0.0
            self.position_label.setText(f"{format_time(output_sec)} / {format_time(self.duration_sec)}")
        else:
            self._update_bars()

    def _on_load_error(self, msg: str):
        self.load_btn.setEnabled(True)
        self.halftime_btn.setEnabled(True)
        self.play_pause_btn.setEnabled(False)
        self.update_timer.stop()
        self.statusBar().showMessage(f"Load error: {msg}", 5000)

    def _toggle_play_pause(self):
        if self.controller.is_playing():
            self.controller.toggle_pause()
            self.play_pause_btn.setText("Play" if self.controller.progress.paused else "Pause")
            return
        if not self.controller.loaded_chunks:
            return
        self.controller.start_playback()
        self.play_pause_btn.setText("Pause")
        self.update_timer.start(UI_POLL_MS)

    def _on_playback_finished(self):
        self.update_timer.stop()
        self._update_bars()
        self.play_pause_btn.setText("Play")

    def _on_playback_error(self, msg: str):
        self.update_timer.stop()
        self.play_pause_btn.setText("Play")
        self.statusBar().showMessage(f"Playback error: {msg}", 5000)

    def _on_slider_pressed(self):
        self._slider_dragging = True

    def _on_slider_moved(self, value: int):
        if self._slider_dragging and self.duration_sec > 0:
            sec = (value / SLIDER_RANGE) * self.duration_sec
            self.position_label.setText(f"{format_time(sec)} / {format_time(self.duration_sec)}")

    def _on_slider_released(self):
        self._slider_dragging = False
        c = self.controller
        if not c.loaded_chunks or not c.is_playing():
            return
        ratio = self.position_slider.value() / SLIDER_RANGE

        def do_seek_and_resume():
            c.seek_to_ratio(ratio)
            self.play_pause_btn.setText("Pause")

        if c.progress.paused:
            do_seek_and_resume()
        else:
            c.progress.paused = True
            self.play_pause_btn.setText("Play")
            QTimer.singleShot(SEEK_DELAY_MS, do_seek_and_resume)

    def _update_bars(self):
        p = self.controller.progress
        if p.sample_rate and p.channels:
            decode_sec = bytes_to_seconds(p.bytes_decoded, p.sample_rate, p.channels)
            output_sec = bytes_to_seconds(p.bytes_written, p.sample_rate, p.channels)
        else:
            decode_sec = output_sec = 0.0
        decode_total = max(self.file_duration, 0.001)
        output_total = max(self.duration_sec, 0.001)
        decode_pct = min(100.0, 100.0 * decode_sec / decode_total)
        if self._reload_preserve is not None:
            ratio, _ = self._reload_preserve
            output_pct = ratio * 100.0
            output_sec = ratio * self.duration_sec
        else:
            output_pct = min(100.0, 100.0 * output_sec / output_total)
        self.decode_bar.setValue(int(decode_pct * 10))
        has_valid_output = self._reload_preserve is not None or (p.sample_rate and p.channels)
        if not self._slider_dragging and has_valid_output:
            self.position_slider.setValue(int(output_pct * 10))
        self.decode_label.setText(f"{format_time(decode_sec)} / {format_time(self.file_duration)}")
        self.position_label.setText(f"{format_time(output_sec)} / {format_time(self.duration_sec)}")


def main():
    app = QApplication(sys.argv)
    win = StreamProgressWindow()

    def on_sigint(*args):
        win._shutdown()

    signal.signal(signal.SIGINT, on_sigint)

    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
