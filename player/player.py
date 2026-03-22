"""
Standalone MP3 player using PyAudio.
Streams an MP3 from the filesystem and plays it (decodes on the fly via ffmpeg).
Samples pass through an optional transform between decode and output.
Requires: pyaudio, numpy, ffmpeg (brew install ffmpeg)
"""

import subprocess
import sys
import time
from pathlib import Path
from typing import Callable

import numpy as np
import pyaudio

CHUNK = 4096
BYTES_PER_SAMPLE = 2  # 16-bit


def _get_audio_info(filepath: Path) -> tuple[int, int]:
    """Get sample rate and channel count via ffprobe."""
    result = subprocess.run(
        [
            "ffprobe",
            "-v", "error",
            "-select_streams", "a:0",
            "-show_entries", "stream=sample_rate,channels",
            "-of", "csv=p=0",
            str(filepath),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    rate_str, channels_str = result.stdout.strip().split(",")
    return int(rate_str), int(channels_str)


def get_duration(filepath: str | Path) -> float:
    """Get duration in seconds via ffprobe."""
    path = Path(filepath)
    result = subprocess.run(
        [
            "ffprobe",
            "-v", "error",
            "-select_streams", "a:0",
            "-show_entries", "format=duration",
            "-of", "csv=p=0",
            str(path),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    return float(result.stdout.strip() or 0)


def _bytes_to_samples(data: bytes, channels: int) -> np.ndarray:
    """Convert raw PCM bytes to float32 samples in range [-1, 1]. Shape: (frames, channels)."""
    int16 = np.frombuffer(data, dtype=np.int16)
    frames = np.reshape(int16, (-1, channels))
    return frames.astype(np.float32) / 32768.0


def _samples_to_bytes(samples: np.ndarray) -> bytes:
    """Convert float32 samples in [-1, 1] back to int16 PCM bytes."""
    clipped = np.clip(samples, -1.0, 1.0)
    int16 = (clipped * 32767).astype(np.int16)
    return int16.tobytes()


def _fade_tail_once(tail_bytes: bytes, channels: int) -> bytes:
    """
    Fade the actual tail once (no repetition). Continuous with the audio,
    avoids the discontinuity that causes a pop. No tiling = no ping-pong.
    """
    if len(tail_bytes) == 0:
        return b""
    samples = np.frombuffer(tail_bytes, dtype=np.int16)
    frames = np.reshape(samples, (-1, channels)).astype(np.float32) / 32768.0
    n = len(frames)
    ramp = np.linspace(1.0, 0.0, n, dtype=np.float32)
    faded = frames * ramp[:, np.newaxis]
    clipped = np.clip(faded, -1.0, 1.0)
    return ((clipped * 32767).astype(np.int16)).tobytes()


def _make_silence(sample_rate: int, channels: int, duration_ms: float) -> bytes:
    """Generate silence (zeros) for given duration."""
    n_frames = int(sample_rate * (duration_ms / 1000))
    if n_frames <= 0:
        return b""
    return b"\x00" * (n_frames * channels * BYTES_PER_SAMPLE)


def _fade_head(head_bytes: bytes, channels: int) -> bytes:
    """Apply fade-in (ramp 0->1) to start of chunk. Used when resuming."""
    if len(head_bytes) == 0:
        return b""
    samples = np.frombuffer(head_bytes, dtype=np.int16)
    frames = np.reshape(samples, (-1, channels)).astype(np.float32) / 32768.0
    n = len(frames)
    ramp = np.linspace(0.0, 1.0, n, dtype=np.float32)
    faded = frames * ramp[:, np.newaxis]
    clipped = np.clip(faded, -1.0, 1.0)
    return ((clipped * 32767).astype(np.int16)).tobytes()


def passthrough(samples: np.ndarray, sample_rate: int, num_channels: int) -> np.ndarray:
    """Default transform: return samples unchanged."""
    return samples

def halftime(samples: np.ndarray, sample_rate: int, num_channels: int) -> np.ndarray:
    """Double each sample (2x length) to play at half tempo."""
    return np.repeat(samples, 2, axis=0)


def preload_mp3(
    filepath: str | Path,
    transform: Callable[[np.ndarray, int, int], np.ndarray] | None = None,
    on_progress: Callable[[int, int, int], None] | None = None,
    abort_check: Callable[[], bool] | None = None,
) -> tuple[list[bytes], int, int]:
    """
    Decode entire file into memory. Returns (chunks, sample_rate, channels).
    on_progress: optional callback(bytes_decoded, sample_rate, channels).
    abort_check: optional callback; if it returns True, stop and return partial chunks.
    """
    path = Path(filepath)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")

    if transform is None:
        transform = passthrough

    sample_rate, channels = _get_audio_info(path)
    bytes_per_chunk = CHUNK * channels * BYTES_PER_SAMPLE

    ffmpeg_proc = subprocess.Popen(
        [
            "ffmpeg",
            "-hide_banner", "-loglevel", "error",
            "-nostdin",
            "-i", str(path),
            "-f", "s16le",
            "-",
        ],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )

    chunks: list[bytes] = []
    bytes_decoded = 0
    try:
        while raw := ffmpeg_proc.stdout.read(bytes_per_chunk):
            if abort_check and abort_check():
                break
            bytes_decoded += len(raw)
            samples = _bytes_to_samples(raw, channels)
            if len(samples) == 0:
                break
            transformed = transform(samples, sample_rate, channels)
            chunks.append(_samples_to_bytes(transformed))
            if on_progress:
                on_progress(bytes_decoded, sample_rate, channels)
    finally:
        ffmpeg_proc.terminate()
        ffmpeg_proc.wait()

    return chunks, sample_rate, channels


def play_from_buffer(
    chunks: list[bytes],
    sample_rate: int,
    channels: int,
    on_progress: Callable[[int, int, int], None] | None = None,
    abort_check: Callable[[], bool] | None = None,
    pause_check: Callable[[], bool] | None = None,
    seek_check: Callable[[], int | None] | None = None,
) -> None:
    """
    Stream preloaded chunks to PyAudio. write() blocks when the output buffer is full,
    so playback is naturally paced without explicit sleeping.
    on_progress: optional callback(bytes_written, sample_rate, channels).
    abort_check: optional callback; if it returns True, stop playback.
    pause_check: optional callback; if it returns True, pause until it returns False.
    seek_check: optional callback; if it returns chunk_index (int), seek to that chunk.
    """
    def _open_stream():
        pa = pyaudio.PyAudio()
        return pa, pa.open(
            format=pyaudio.paInt16,
            channels=channels,
            rate=sample_rate,
            output=True,
        )

    def _apply_seek(seek_to: int):
        nonlocal p, stream, bytes_written, i, last_chunk, just_resumed
        stream.stop_stream()
        stream.close()
        p.terminate()
        p, stream = _open_stream()
        bytes_written = sum(len(c) for c in chunks[:seek_to])
        i = seek_to
        last_chunk = b""
        just_resumed = True

    p, stream = _open_stream()
    bytes_written = 0
    last_chunk = b""
    just_resumed = False
    i = 0
    try:
        while i < len(chunks):
            seek_to = seek_check() if seek_check else None
            if seek_to is not None and 0 <= seek_to < len(chunks):
                _apply_seek(seek_to)
                continue
            chunk = chunks[i]
            if abort_check and abort_check():
                break
            while pause_check and pause_check():
                fade = _fade_tail_once(last_chunk, channels) if last_chunk else b""
                if fade:
                    stream.write(fade)
                pad = _make_silence(sample_rate, channels, 60)
                stream.write(pad)
                drain_s = (len(fade) + len(pad)) / (sample_rate * channels * BYTES_PER_SAMPLE)
                time.sleep(drain_s + 0.25)
                stream.stop_stream()
                while pause_check() and not (abort_check and abort_check()):
                    time.sleep(0.05)
                if abort_check and abort_check():
                    break
                seek_to = seek_check() if seek_check else None
                if seek_to is not None and 0 <= seek_to < len(chunks):
                    _apply_seek(seek_to)
                    continue
                stream.start_stream()
                just_resumed = True
            if abort_check and abort_check():
                break
            chunk_len = len(chunk)
            # Fade in after resume to avoid click when stream restarts
            if just_resumed and chunk:
                just_resumed = False
                head_ms = 50
                head_frames = min(chunk_len // (channels * BYTES_PER_SAMPLE),
                                 int(sample_rate * head_ms / 1000))
                head_bytes = head_frames * channels * BYTES_PER_SAMPLE
                if head_bytes > 0 and head_bytes < chunk_len:
                    stream.write(_fade_head(chunk[:head_bytes], channels))
                    stream.write(chunk[head_bytes:])
                elif head_bytes >= chunk_len and chunk_len > 0:
                    stream.write(_fade_head(chunk, channels))
                else:
                    stream.write(chunk)
            else:
                stream.write(chunk)
            last_chunk = chunk
            bytes_written += chunk_len
            i += 1
            if on_progress:
                on_progress(bytes_written, sample_rate, channels)
    finally:
        stream.stop_stream()
        stream.close()
        p.terminate()


if __name__ == "__main__":
    print("Run the GUI with: python -m player.gui")
