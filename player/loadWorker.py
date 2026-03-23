"""LoadWorker runs in the GUI process. Loads files, runs tempo/waveform, sends buffer to RT via shared memory."""
import uuid
from pathlib import Path

import numpy as np
from PySide6.QtCore import QThread, Signal
from multiprocessing import shared_memory

from mp3Loader import Mp3Loader
from audioBuffer import AudioBuffer
from tempoDetector import TempoDetector
from waveformUtil import buffer_to_waveform
from commandUtil import CommandUtil


class LoadWorker(QThread):
	"""Loads audio in GUI process, computes tempo and waveform, ships raw data to RT via shared memory."""
	error = Signal(str)

	def __init__(self, path: Path, command_util: CommandUtil):
		super().__init__()
		self.path = path
		self.command_util = command_util

	def run(self):
		shm = None
		try:
			loader = Mp3Loader()
			buffer = [None]  # mutable to capture from callback

			def on_progress(p: float):
				self.command_util.send_status({"type": "load_progress", "progress": p})

			def on_success(b: AudioBuffer):
				buffer[0] = b

			loader.load(
				self.path,
				progressCallback=on_progress,
				successCallback=on_success,
			)

			if buffer[0] is None:
				self.error.emit("Load failed")
				return

			buf = buffer[0]
			# Use actual decoded length; ffprobe duration can differ from ffmpeg output
			sample_len = buf.write_pos // 2  # stereo frames
			duration = sample_len / 44100.0

			# Heavy work: tempo and waveform (off the RT process)
			tempo = TempoDetector().detect(buf.buffer[:buf.write_pos])
			waveform = buffer_to_waveform(buf, width=1024)

			# Copy into shared memory for RT process
			n_bytes = sample_len * 2 * 4  # stereo float32
			shm_name = f"audio_{uuid.uuid4().hex[:12]}"
			shm = shared_memory.SharedMemory(create=True, size=n_bytes, name=shm_name)
			arr = np.ndarray((sample_len * 2,), dtype=np.float32, buffer=shm.buf)
			arr[:] = buf.buffer[:buf.write_pos]

			# RT process attaches and creates AudioTrack; GUI gets waveform/tempo
			self.command_util.send_command({
				"command": "track_ready",
				"shm_name": shm_name,
				"sample_len": sample_len,
			})
			self.command_util.send_status({
				"type": "load_status",
				"status": "success",
				"waveform": waveform,
				"duration": duration,
				"tempo": tempo,
			})
		except Exception as e:
			self.error.emit(str(e))
		finally:
			if shm is not None:
				shm.close()
