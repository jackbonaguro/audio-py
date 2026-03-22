"""Waveform computation from PCM audio. Used by both in-process and multiprocess flows."""
import numpy as np

from audioBuffer import AudioBuffer


def buffer_to_waveform(buffer: AudioBuffer, width: int) -> np.ndarray:
	"""Compute mins/maxs per pixel from an AudioBuffer. Shape: (width, 2)."""
	if not buffer or buffer.sample_len <= 0:
		return np.zeros((width, 2), dtype=np.float32)
	frames = np.reshape(buffer.buffer[:buffer.write_pos], (-1, 2))
	mono = frames.mean(axis=1).astype(np.float32)
	n = len(mono)
	if n == 0:
		return np.zeros((width, 2), dtype=np.float32)
	samples_per_pixel = max(1, n // width)
	mins = np.zeros(width, dtype=np.float32)
	maxs = np.zeros(width, dtype=np.float32)
	for i in range(width):
		start = i * samples_per_pixel
		end = min((i + 1) * samples_per_pixel, n)
		if start < end:
			mins[i] = mono[start:end].min()
			maxs[i] = mono[start:end].max()
	return np.column_stack((mins, maxs))
