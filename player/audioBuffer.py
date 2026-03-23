import numpy as np

# Our main audio buffer class.
# Always 2-channel stereo float32 audio @ 44100Hz.

class AudioBuffer:
	def __init__(self, sample_len: int):
		self.sample_len = sample_len
		self.buffer = np.zeros(sample_len * 2, dtype=np.float32)
		self.write_pos = 0

	def add_samples(self, samples: np.ndarray):
		"""Append float32 samples (shape: frames, channels) to the buffer."""
		flat = samples.flatten()
		n = len(flat)
		space = len(self.buffer) - self.write_pos
		to_copy = min(n, max(0, space))
		if to_copy > 0:
			self.buffer[self.write_pos : self.write_pos + to_copy] = flat[:to_copy]
			self.write_pos += to_copy
