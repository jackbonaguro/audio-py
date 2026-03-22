"""
Playback controller: owns workers, state, and coordinates load/play/seek.
"""

from pathlib import Path

from PySide6.QtCore import QObject, QThread, Signal

try:
    from .player import preload_mp3, play_from_buffer, passthrough, halftime
    from .state import ProgressState
    from .utils import ratio_to_chunk_index
except ImportError:
    from player import preload_mp3, play_from_buffer, passthrough, halftime
    from state import ProgressState
    from utils import ratio_to_chunk_index


class PreloadWorker(QThread):
    finished = Signal()
    error = Signal(str)
    complete = Signal(list, int, int)

    def __init__(self, filepath: Path, progress: ProgressState, transform=None):
        super().__init__()
        self.filepath = filepath
        self.progress = progress
        self.transform = transform or passthrough

    def run(self):
        try:
            chunks, sample_rate, channels = preload_mp3(
                self.filepath,
                transform=self.transform,
                on_progress=lambda b, sr, ch: self._on_progress(b, sr, ch),
                abort_check=lambda: self.progress.abort,
            )
            if self.progress.abort:
                return
            self.complete.emit(chunks, sample_rate, channels)
        except Exception as e:
            self.error.emit(str(e))
        finally:
            self.progress.done = True
            self.finished.emit()

    def _on_progress(self, bytes_decoded: int, sample_rate: int, channels: int):
        self.progress.bytes_decoded = bytes_decoded
        self.progress.sample_rate = sample_rate
        self.progress.channels = channels


class PlaybackWorker(QThread):
    finished = Signal()
    error = Signal(str)

    def __init__(self, chunks: list[bytes], sample_rate: int, channels: int, progress: ProgressState):
        super().__init__()
        self.chunks = chunks
        self.sample_rate = sample_rate
        self.channels = channels
        self.progress = progress

    def run(self):
        try:
            play_from_buffer(
                self.chunks, self.sample_rate, self.channels,
                on_progress=lambda b, sr, ch: self._on_progress(b, sr, ch),
                abort_check=lambda: self.progress.abort,
                pause_check=lambda: self.progress.paused,
                seek_check=self._seek_check,
            )
        except Exception as e:
            self.error.emit(str(e))
        finally:
            self.progress.done = True
            self.finished.emit()

    def _on_progress(self, bytes_written: int, sample_rate: int, channels: int):
        self.progress.bytes_written = bytes_written
        self.progress.sample_rate = sample_rate
        self.progress.channels = channels

    def _seek_check(self) -> int | None:
        s = self.progress.seek_to_chunk
        if s is not None:
            self.progress.seek_to_chunk = None
            return s
        return None


class PlaybackController(QObject):
    load_complete = Signal(list, int, int)
    load_error = Signal(str)
    load_finished = Signal()
    playback_finished = Signal()
    playback_error = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.progress = ProgressState()
        self.preload_worker: PreloadWorker | None = None
        self.playback_worker: PlaybackWorker | None = None
        self.loaded_chunks: list[bytes] | None = None
        self.loaded_sample_rate = 0
        self.loaded_channels = 0

    def is_loading(self) -> bool:
        return self.preload_worker is not None and self.preload_worker.isRunning()

    def is_playing(self) -> bool:
        return self.playback_worker is not None and self.playback_worker.isRunning()

    def load(self, path: Path, transform):
        """Start preloading. Aborts any running playback first."""
        if self.is_loading():
            return False
        self._abort_playback()
        self.progress.bytes_decoded = 0
        self.progress.bytes_written = 0
        self.progress.done = False
        self.progress.abort = False
        self.loaded_chunks = None
        self.preload_worker = PreloadWorker(path, self.progress, transform)
        self.preload_worker.finished.connect(self._on_load_finished)
        self.preload_worker.error.connect(self._on_load_error)
        self.preload_worker.complete.connect(self._on_load_complete)
        self.preload_worker.start()
        return True

    def _on_load_complete(self, chunks: list[bytes], sample_rate: int, channels: int):
        self.loaded_chunks = chunks
        self.loaded_sample_rate = sample_rate
        self.loaded_channels = channels
        self.load_complete.emit(chunks, sample_rate, channels)

    def _on_load_finished(self):
        self.preload_worker = None
        self.load_finished.emit()

    def _on_load_error(self, msg: str):
        self.preload_worker = None
        self.load_error.emit(msg)

    def start_playback(self, restore_ratio: float | None = None, restore_was_playing: bool = False):
        """Start or resume playback. If restore_ratio is set, seek to that position first."""
        if not self.loaded_chunks:
            return
        self.progress.done = False
        self.progress.abort = False
        self.progress.paused = False
        self.progress.seek_to_chunk = None
        if restore_ratio is not None:
            chunk_index = ratio_to_chunk_index(self.loaded_chunks, restore_ratio)
            self.progress.bytes_written = sum(len(c) for c in self.loaded_chunks[:chunk_index])
            self.progress.seek_to_chunk = chunk_index
        else:
            self.progress.bytes_written = 0
        self.playback_worker = PlaybackWorker(
            self.loaded_chunks, self.loaded_sample_rate, self.loaded_channels, self.progress
        )
        self.playback_worker.finished.connect(self._on_playback_finished)
        self.playback_worker.error.connect(self._on_playback_error)
        self.playback_worker.start()
        if restore_was_playing:
            self.progress.paused = False

    def _on_playback_finished(self):
        self.playback_worker = None
        self.playback_finished.emit()

    def _on_playback_error(self, msg: str):
        self.playback_worker = None
        self.playback_error.emit(msg)

    def toggle_pause(self):
        if self.is_playing():
            self.progress.paused = not self.progress.paused

    def seek_to_ratio(self, ratio: float):
        """Set seek target for when playback is active. Caller should ensure loaded_chunks exists."""
        if not self.loaded_chunks:
            return
        chunk_index = ratio_to_chunk_index(self.loaded_chunks, ratio)
        self.progress.seek_to_chunk = chunk_index
        self.progress.paused = False

    def _abort_playback(self):
        if not self.is_playing():
            return
        self.progress.abort = True
        self.playback_worker.wait(3000)
        self.progress.abort = False
        self.playback_worker = None

    def abort(self):
        """For shutdown: abort and wait for workers."""
        self.progress.abort = True
        for w in (self.preload_worker, self.playback_worker):
            if w and w.isRunning():
                w.wait(5000)
