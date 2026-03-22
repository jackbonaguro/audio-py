from pathlib import Path
import numpy as np
import pyaudio

from PySide6.QtCore import QObject, QThread, Signal

from mp3Loader import Mp3Loader
from audioBuffer import AudioBuffer
from audioTrack import AudioTrack

class LoadWorker(QThread):
	progress = Signal(float)
	success = Signal(object)  # AudioBuffer
	error = Signal(str)
	finished_signal = Signal()

	def __init__(self, path: Path):
		super().__init__()
		self.path = path

	def run(self):
		try:
			loader = Mp3Loader()
			loader.load(
				self.path,
				progressCallback=lambda p: self.progress.emit(p),
				successCallback=lambda b: self.success.emit(b),
			)
		except Exception as e:
			self.error.emit(str(e))
		finally:
			self.finished_signal.emit()


class AudioEngine(QObject):
	track: AudioTrack | None = None
	fileLoaded = Signal()

	def __init__(self):
		super().__init__()
		self._load_worker: LoadWorker | None = None
		self._pa = pyaudio.PyAudio()
		self._stream = self._pa.open(
			format=pyaudio.paFloat32,
			channels=2,
			rate=44100,
			output=True,
			stream_callback=self._stream_callback,
		)

	def _stream_callback(self, in_data, frame_count, time_info, status):
		"""Called by PyAudio when it needs more samples."""
		stereo = self.get_samples(frame_count)
		return (stereo.astype(np.float32).tobytes(), pyaudio.paContinue)

	def load_file(self, path: Path):
		if self._load_worker is not None and self._load_worker.isRunning():
			return
		self._load_worker = LoadWorker(path)
		self._load_worker.progress.connect(self.on_progress)
		self._load_worker.success.connect(self.on_success)
		self._load_worker.error.connect(self._on_load_error)
		self._load_worker.finished_signal.connect(self._on_load_finished)
		self._load_worker.start()

	def on_progress(self, progress: float):
		print(f"Progress: {progress}")

	def on_success(self, buffer: AudioBuffer):
		print(f"Success: {buffer}")
		self.track = AudioTrack(buffer)
		self.fileLoaded.emit()
	
	def get_track(self) -> AudioTrack | None:
		return self.track

	def _on_load_error(self, msg: str):
		print(f"Load error: {msg}")

	def _on_load_finished(self):
		self._load_worker = None

	def play_track(self):
		self.track.playing = True

	def pause_track(self):
		self.track.playing = False

	def stop_track(self):
		self.track.playing = False
		self.track.position = 0

	# Real time stuff down here. The audio output stream is always open, and always requesting samples.
	# For now we just have one track, so we delegate getting samples from it.
	def get_samples(self, frame_count: int) -> np.ndarray:
		if self.track is None:
			return np.zeros(frame_count * 2, dtype=np.float32)
		return self.track.get_samples_at_speed(frame_count)
	
	
