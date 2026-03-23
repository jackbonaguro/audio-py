from typing import Protocol

import numpy as np


class AudioSource(Protocol):
    """Pull-based mono audio source. Returns up to n_frames samples; may return fewer."""

    def pull(self, n_frames: int) -> tuple[np.ndarray, bool]:
        """Return (samples, finished). Samples is float32, length <= n_frames."""
        ...

    def seek(self, pos: int):
        """Seek to frame position in the underlying source. Resets internal state."""
        ...
