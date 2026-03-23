"""
Rubberband-based real-time time stretcher.
- Stereo-aware (no per-channel split)
- Overlap-add with Hann windows
- Normalized overlap to preserve amplitude
- Smooth and artifact-free output at any speed
"""

import numpy as np
import rubberband

SAMPLE_RATE = 44100
CHUNK_FRAMES = 4096 * 3       # Larger blocks for context
OVERLAP = 0.5             # 50% overlap
STEP_FRAMES = int(CHUNK_FRAMES * (1 - OVERLAP))
MIN_INPUT_FRAMES = CHUNK_FRAMES + STEP_FRAMES

CRISPNESS = 2
USE_FORMANTS = True
USE_PRECISE = True


def _stretch_stereo_block(stereo: np.ndarray, ratio: float) -> np.ndarray:
    """Stretch stereo audio block using Rubber Band in stereo mode."""
    return np.asarray(
        rubberband.stretch(
            stereo.astype(np.float32),
            rate=SAMPLE_RATE,
            ratio=ratio,
            crispness=CRISPNESS,
            formants=USE_FORMANTS,
            precise=USE_PRECISE,
        ),
        dtype=np.float32,
    )


def _hann_window(length: int) -> np.ndarray:
    """Generate a Hann window."""
    if length <= 1:
        return np.ones(max(length, 1), dtype=np.float32)
    return 0.5 * (1 - np.cos(2 * np.pi * np.arange(length, dtype=np.float32) / (length - 1)))


def _overlap_add_normalized(chunk0: np.ndarray, chunk1: np.ndarray, ratio: float) -> np.ndarray:
    """
    Overlap-add two stretched chunks with normalized Hann windows.
    chunk0: first chunk
    chunk1: second chunk
    ratio: stretch ratio
    """
    n0 = len(chunk0) // 2
    n1 = len(chunk1) // 2
    offset = int(STEP_FRAMES * ratio)
    total_frames = max(offset + n1, n0)
    total_samples = total_frames * 2

    out = np.zeros(total_samples, dtype=np.float32)
    window0 = _hann_window(len(chunk0))
    window1 = _hann_window(len(chunk1))
    weight = np.zeros(total_samples, dtype=np.float32)

    # Add chunk0
    out[:len(chunk0)] += chunk0 * window0
    weight[:len(chunk0)] += window0

    # Add chunk1 at offset
    dst_start = offset * 2
    dst_end = dst_start + len(chunk1)
    out[dst_start:dst_end] += chunk1 * window1
    weight[dst_start:dst_end] += window1

    # Normalize to avoid amplitude dips
    nonzero = weight > 1e-6
    out[nonzero] /= weight[nonzero]

    return out


class RubberbandStretcher:
    """Stereo, pitch-preserving time stretcher with overlap-add smoothing."""

    def __init__(self):
        self.input_buffer = np.zeros(0, dtype=np.float32)
        self.output_buffer = np.zeros(0, dtype=np.float32)
        self.speed = 1.0

    def on_seek(self) -> None:
        self.input_buffer = np.zeros(0, dtype=np.float32)
        self.output_buffer = np.zeros(0, dtype=np.float32)

    def stretch(self, source_stereo: np.ndarray, output_frame_count: int, speed: float) -> np.ndarray:
        """Append input, process overlapping chunks, and return output_frame_count frames."""
        self.speed = speed
        ratio = 1.0 / speed if speed > 0 else 1.0

        source_frames = len(source_stereo) // 2
        if source_frames == 0:
            return self._drain(output_frame_count)

        # Append input to buffer
        self.input_buffer = np.concatenate([self.input_buffer, source_stereo])
        input_frames = len(self.input_buffer) // 2

        # Process overlapping chunks
        while input_frames >= MIN_INPUT_FRAMES:
            chunk0 = self.input_buffer[: CHUNK_FRAMES * 2].copy()
            chunk1 = self.input_buffer[STEP_FRAMES * 2 : MIN_INPUT_FRAMES * 2].copy()

            stretched0 = _stretch_stereo_block(chunk0, ratio)
            stretched1 = _stretch_stereo_block(chunk1, ratio)

            combined = _overlap_add_normalized(stretched0, stretched1, ratio)
            self.output_buffer = np.concatenate([self.output_buffer, combined])

            self.input_buffer = self.input_buffer[STEP_FRAMES * 2 :]
            input_frames -= STEP_FRAMES

        # Leftover small chunk
        if len(self.output_buffer) < output_frame_count * 2 and input_frames > 0:
            chunk = self.input_buffer.copy()
            self.input_buffer = np.zeros(0, dtype=np.float32)
            stretched = _stretch_stereo_block(chunk, ratio)
            self.output_buffer = np.concatenate([self.output_buffer, stretched])

        return self._drain(output_frame_count)

    def _drain(self, n: int) -> np.ndarray:
        """Return n frames from output buffer, zero-pad if needed."""
        result = self.output_buffer[: n * 2].copy()
        self.output_buffer = self.output_buffer[n * 2 :]
        if len(result) < n * 2:
            padded = np.zeros(n * 2, dtype=np.float32)
            padded[: len(result)] = result
            return padded
        return result
