import numpy as np

from .audio_source import AudioSource


def _resample(x: np.ndarray, num: int) -> np.ndarray:
    """Resample x to num samples via linear interpolation (avoids slow scipy import)."""
    if len(x) == num:
        return x.astype(np.float32)
    indices = np.linspace(0, len(x) - 1, num, endpoint=True)
    return np.interp(indices, np.arange(len(x), dtype=np.float32), x).astype(
        np.float32
    )


class ResampleSource:
    """Mono only. For stereo, create two instances."""

    def __init__(
        self,
        source: AudioSource,
        pitch_ratio: float,
    ):
        self.source = source
        self.pitch_ratio = pitch_ratio
        self.buffer = np.array([], dtype=np.float32)
        self.finished = False

    def set_ratio(self, pitch_ratio: float):
        """Update pitch ratio for live pitch shifting."""
        self.pitch_ratio = pitch_ratio

    def seek(self, pos: int):
        """Seek to frame position. Clears buffer and seeks underlying source."""
        self.source.seek(pos)
        self.buffer = np.array([], dtype=np.float32)
        self.finished = False

    def pull(self, n_frames: int) -> tuple[np.ndarray, bool]:
        need_stretched = int(np.ceil(n_frames * self.pitch_ratio))

        while len(self.buffer) < need_stretched and not self.finished:
            pull_count = max(need_stretched - len(self.buffer), 4096)
            chunk, self.finished = self.source.pull(pull_count)
            if len(chunk) > 0:
                self.buffer = np.concatenate([self.buffer, chunk])

        if len(self.buffer) < need_stretched:
            available = len(self.buffer)
            if available == 0:
                return np.array([], dtype=np.float32), self.finished
            n_out = max(0, int(available / self.pitch_ratio))
            if n_out == 0:
                return np.array([], dtype=np.float32), self.finished
            take_stretched = available
        else:
            n_out = n_frames
            take_stretched = need_stretched

        stretch_chunk = self.buffer[:take_stretched].copy()
        self.buffer = self.buffer[take_stretched:]
        resampled = _resample(stretch_chunk, n_out)
        return resampled, self.finished
