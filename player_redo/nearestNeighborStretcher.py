"""
Nearest-neighbor resampling. Lower quality, less CPU.
"""

import numpy as np
from lerpStretcher import TimeStretchAdapter


class NearestNeighborStretcher:
	"""Resampling-based time stretch using nearest-neighbor interpolation."""

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

		indices = np.round(
			np.linspace(0, source_frame_count - 1, output_frame_count)
		).astype(np.intp)

		scaled_stereo = np.empty(output_frame_count * 2, dtype=np.float32)
		scaled_stereo[0::2] = left[indices]
		scaled_stereo[1::2] = right[indices]

		return scaled_stereo
