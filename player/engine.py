from multiprocessing import shared_memory
import numpy as np
import pyaudio

from PySide6.QtCore import QObject, Signal

from audioTrack import AudioTrack
from typing import Callable

from commandUtil import CommandUtil


class _ShmBuffer:
	"""Minimal buffer-like wrapper for shared-memory-backed audio data."""
	def __init__(self, arr: np.ndarray, sample_len: int):
		self.buffer = arr
		self.sample_len = sample_len
		self.write_pos = sample_len


class AudioEngine(QObject):
	tracks: dict[int, AudioTrack] = {}
	fileLoaded = Signal()
	on_position_update: Callable[[float, int], None] | None = None

	def __init__(self, command_util: CommandUtil):
		super().__init__()
		self.command_util = command_util
		self._current_shm: shared_memory.SharedMemory | None = None
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

	def load_from_shared_memory(self, shm_name: str, sample_len: int, track_id: int):
		"""Create AudioTrack from shared memory. Caller (GUI) does load/tempo/waveform."""
		if self._current_shm is not None:
			self._current_shm.close()
			try:
				self._current_shm.unlink()
			except OSError:
				pass
			self._current_shm = None

		shm = shared_memory.SharedMemory(name=shm_name)
		self._current_shm = shm
		arr = np.ndarray((sample_len * 2,), dtype=np.float32, buffer=shm.buf)
		buffer_wrapper = _ShmBuffer(arr, sample_len)
		self.tracks[track_id] = AudioTrack(track_id, buffer_wrapper, self.command_util)
		self.fileLoaded.emit()

	def get_track(self, track_id: int) -> AudioTrack | None:
		return self.tracks[track_id]

	def play_track(self, track_id: int):
		if track_id in self.tracks:
			self.tracks[track_id].playing = True

	def pause_track(self, track_id: int):
		if track_id in self.tracks:
			self.tracks[track_id].playing = False

	def stop_track(self, track_id: int):
		if track_id in self.tracks:
			self.tracks[track_id].playing = False
			self.tracks[track_id].seek(0)  # Reset position and propagate to source chain
			self.command_util.send_status({"type": "track_stopped", "track_id": track_id})

	def seek_track(self, track_id: int, position: float):
		if track_id in self.tracks:
			self.tracks[track_id].seek(position)

	def set_track_speed(self, track_id: int, speed: float):
		if track_id in self.tracks:
			self.tracks[track_id].set_speed(speed)

	def set_track_pitch(self, track_id: int, pitch_semitones: float):
		if track_id in self.tracks:
			self.tracks[track_id].set_pitch(pitch_semitones)

	# Real time stuff down here. The audio output stream is always open, and always requesting samples.
	# For now we just have one track, so we delegate getting samples from it.
	def get_samples(self, frame_count: int) -> np.ndarray:
		if len(self.tracks) == 0:
			return np.zeros(frame_count * 2, dtype=np.float32)

		stereo = np.zeros(frame_count * 2, dtype=np.float32)
		for track_id, track in self.tracks.items():
			if track.playing:
				stereo += track.get_samples(frame_count)
			self.on_position_update(track.position / track.SAMPLE_RATE, track_id)

		return stereo

	# IPC Signals
	def set_on_position_update(self, callback: Callable[[float, int], None]):
		self.on_position_update = callback
	
	
