"""Shared utilities for the player."""

BYTES_PER_SAMPLE = 2  # 16-bit
SLIDER_RANGE = 1000
UI_POLL_MS = 50
SEEK_DELAY_MS = 10


def format_time(sec: float) -> str:
    """Format seconds as M:SS."""
    m = int(sec // 60)
    s = int(sec % 60)
    return f"{m}:{s:02d}"


def bytes_to_seconds(bytes_val: int, sample_rate: int, channels: int) -> float:
    """Convert PCM bytes to playback time in seconds."""
    return bytes_val / (sample_rate * channels * BYTES_PER_SAMPLE)


def bytes_to_chunk_index(chunks: list[bytes], target_bytes: int) -> int:
    """Return chunk index such that sum(len(chunks[:i])) > target_bytes, or last index."""
    cum = 0
    for i, c in enumerate(chunks):
        cum += len(c)
        if cum > target_bytes:
            return i
    return len(chunks) - 1 if chunks else 0


def ratio_to_chunk_index(chunks: list[bytes], ratio: float) -> int:
    """Return chunk index for given position ratio (0-1)."""
    total = sum(len(c) for c in chunks)
    if total <= 0:
        return len(chunks) - 1 if chunks else 0
    target_bytes = int(max(0, min(1, ratio)) * total)
    return bytes_to_chunk_index(chunks, target_bytes)
