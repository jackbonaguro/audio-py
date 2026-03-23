from pathlib import Path
import numpy as np
import pyaudio

from PySide6.QtCore import QObject, QThread, Signal

from mp3Loader import Mp3Loader
from audioBuffer import AudioBuffer
from audioTrack import AudioTrack
from typing import Callable

from commandUtil import CommandUtil
from waveformUtil import buffer_to_waveform

class LoadWorker(QThread):
	progress = Signal(float)
	success = Signal(object)  # AudioBuffer
	error = Signal(str)

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
			pass


class AudioEngine(QObject):
	track: AudioTrack | None = None
	fileLoaded = Signal()
	on_position_update: Callable[[float], None] | None = None

	def __init__(self, command_util: CommandUtil):
		super().__init__()
		self.command_util = command_util
		self._load_worker: LoadWorker | None = None
		self._pa = pyaudio.PyAudio()
		self._stream = self._pa.open(
			format=pyaudio.paFloat32,
			channels=2,
			rate=44100,
			output=True,
			stream_callback=self._stream_callback,
			frames_per_buffer=2048,
		)
		self._stream.start_stream()

	def _stream_callback(self, in_data, frame_count, time_info, status):
		"""Called by PyAudio when it needs more samples."""
		try:
			stereo = self.get_samples(frame_count)
			return (stereo.astype(np.float32).tobytes(), pyaudio.paContinue)
		except Exception as e:
			print(f"Stream callback error: {e}", flush=True)
			import traceback
			traceback.print_exc()
			return (np.zeros(frame_count * 2, dtype=np.float32).tobytes(), pyaudio.paContinue)

	def load_file(self, path: str):
		raw_path = Path(path)
		if self._load_worker is not None and self._load_worker.isRunning():
			return
		self._load_worker = LoadWorker(raw_path)
		self._load_worker.progress.connect(self.on_progress)
		self._load_worker.success.connect(self.on_success)
		self._load_worker.error.connect(self._on_load_error)
		self._load_worker.start()

	def on_progress(self, progress: float):
		self.command_util.send_status({"type": "load_progress", "progress": progress})

	def on_success(self, buffer: AudioBuffer):
		self.track = AudioTrack(buffer, self.command_util)
		self.fileLoaded.emit()

		# Compute waveform on RT process and send to main for display (audio data stays here)
		waveform = buffer_to_waveform(buffer, width=1024)
		self.command_util.send_status({"type": "load_status", "status": "success", "waveform": waveform, "duration": self.track.duration})
	
	def get_track(self) -> AudioTrack | None:
		return self.track

	def _on_load_error(self, msg: str):
		print(f"Load error: {msg}")

	def play_track(self):
		if self.track is not None:
			self.track.playing = True

	def pause_track(self):
		if self.track is not None:
			self.track.playing = False

	def stop_track(self):
		if self.track is not None:
			self.track.playing = False
			self.track.position = 0
			self.command_util.send_status({"type": "track_stopped"})

	def seek_track(self, position: float):
		if self.track is not None:
			self.track.seek(position)

	def set_track_speed(self, speed: float):
		if self.track is not None:
			self.track.set_speed(speed)

	# Real time stuff down here. The audio output stream is always open, and always requesting samples.
	# For now we just have one track, so we delegate getting samples from it.
	def get_samples(self, frame_count: int) -> np.ndarray:
		if self.track is None:
			return np.zeros(frame_count * 2, dtype=np.float32)
		stereo = self.track.get_samples(frame_count)
		if self.on_position_update is not None:
			self.on_position_update(self.track.position / self.track.SAMPLE_RATE)
		return stereo

	# IPC Signals
	def set_on_position_update(self, callback: Callable[[float], None]):
		self.on_position_update = callback
	
	
