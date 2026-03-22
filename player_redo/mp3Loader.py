import subprocess
from pathlib import Path
from typing import Callable

import numpy as np

from audioBuffer import AudioBuffer

CHUNK_BYTES = 16384  # Match original player: 4096 frames * 2 channels * 2 bytes


def _bytes_to_samples(data: bytes, channels: int) -> np.ndarray:
	"""Convert raw PCM int16 bytes to float32 samples in [-1, 1]. Shape: (frames, channels)."""
	int16 = np.frombuffer(data, dtype=np.int16)
	frames = np.reshape(int16, (-1, channels))
	return frames.astype(np.float32) / 32768.0


# MP3 Loader
# Loads an mp3 file into a memory buffer when called.
# Returns access to the buffer, as well as a progress callback.

class Mp3Loader:
	def __init__(self):
		pass

	def load(
		self,
		path: Path,
		progressCallback: Callable[[float], None] | None = None,
		successCallback: Callable[[AudioBuffer], None] | None = None
	):
		samples_decoded = 0.0

		# Get metadata, crucially length in samples
		sample_len = self.get_file_sample_len(path)
		buffer = AudioBuffer(sample_len)

		# Actually begin the loading
		ffmpeg_proc = subprocess.Popen(
			[
				"ffmpeg",
				"-hide_banner", "-loglevel", "error",
				"-nostdin",
				"-i", str(path),
				"-f", "s16le",
				"-",
			],
			stdin=subprocess.DEVNULL,
			stdout=subprocess.PIPE,
			stderr=subprocess.DEVNULL,
			start_new_session=True,
		)

		try:
			last_reported = -1.0
			while raw := ffmpeg_proc.stdout.read(CHUNK_BYTES):
				samples_decoded += len(raw) / 2
				samples = _bytes_to_samples(raw, 2)
				if len(samples) == 0:
					break
				buffer.add_samples(samples)
				if progressCallback:
					progress = self.get_progress(samples_decoded, sample_len)
					# Throttle: only report when progress advances by at least 1%
					if progress - last_reported >= 0.01 or progress >= 1.0:
						last_reported = progress
						progressCallback(progress)
		finally:
			ffmpeg_proc.terminate()
			ffmpeg_proc.wait()
			if successCallback:
				successCallback(buffer)

	def get_progress(self, samples_decoded: float, sample_len: int) -> float:
		if sample_len <= 0:
			return 1.0
		ratio = samples_decoded / sample_len
		return round(max(0.0, min(1.0, ratio)), 2)

	def get_file_sample_len(self, path: Path):
		processed_path = Path(path)
		result = subprocess.run(
			[
				"ffprobe",
				"-v", "error",
				"-select_streams", "a:0",
				"-show_entries", "format=duration",
				"-of", "csv=p=0",
				str(processed_path),
			],
			capture_output=True,
			text=True,
			check=True,
		)
		duration = float(result.stdout.strip() or 0)
		return int(duration * 44100)
