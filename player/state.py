"""Shared playback state."""

from dataclasses import dataclass


@dataclass
class ProgressState:
    """Mutable state shared between GUI and workers for load/playback progress."""
    bytes_decoded: int = 0
    bytes_written: int = 0
    sample_rate: int = 0
    channels: int = 0
    done: bool = False
    abort: bool = False
    paused: bool = False
    seek_to_chunk: int | None = None
