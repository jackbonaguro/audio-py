import numpy as np

from audio_source import AudioSource


class RawDataSource:
    """Pull-based mono source from a pre-loaded numpy array (float32)."""

    def __init__(self, data: np.ndarray):
        self._data = np.ascontiguousarray(data, dtype=np.float32)
        self._pos = 0

    def pull(self, n_frames: int) -> tuple[np.ndarray, bool]:
        if self._pos >= len(self._data):
            return np.array([], dtype=np.float32), True
        take = min(n_frames, len(self._data) - self._pos)
        chunk = self._data[self._pos : self._pos + take].copy()
        self._pos += take
        return chunk, self._pos >= len(self._data)
