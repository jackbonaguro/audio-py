"""
Linear interpolation resampling. Higher quality, more CPU.
"""

import numpy as np
from typing import Protocol


class TimeStretchAdapter(Protocol):
	"""Adapter interface for time-stretch algorithms. Accepts source stereo
	(interleaved float32) and produces output_frame_count frames.
	Input length encodes speed: typically source has output_frame_count * speed frames.
	"""

	def stretch(
		self,
		source_stereo: np.ndarray,
		output_frame_count: int,
		speed: float = 1.0,
	) -> np.ndarray:
		...


class LerpStretcher:
	"""Resampling-based time stretch using linear interpolation."""

	def stretch(
		self,
		source_stereo: np.ndarray,
		output_frame_count: int,
		speed: float = 1.0,
	) -> np.ndarray:
		source_frame_count = len(source_stereo) // 2
		if source_frame_count == 0:
			return np.zeros(output_frame_count * 2, dtype=np.float32)

		left = source_stereo[0::2]
		right = source_stereo[1::2]

		sample_positions = np.linspace(
			0, source_frame_count - 1, output_frame_count, dtype=np.float32
		)
		xp = np.arange(source_frame_count, dtype=np.float32)

		scaled_stereo = np.empty(output_frame_count * 2, dtype=np.float32)
		scaled_stereo[0::2] = np.interp(sample_positions, xp, left)
		scaled_stereo[1::2] = np.interp(sample_positions, xp, right)

		return scaled_stereo
