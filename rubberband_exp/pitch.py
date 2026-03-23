import time
import numpy as np
import rubberband
import pyaudio
import soundfile as sf
FORMAT = pyaudio.paFloat32


def _resample(x: np.ndarray, num: int) -> np.ndarray:
    """Resample x to num samples via linear interpolation (avoids slow scipy import)."""
    if len(x) == num:
        return x.astype(np.float32)
    indices = np.linspace(0, len(x) - 1, num, endpoint=True)
    return np.interp(indices, np.arange(len(x), dtype=np.float32), x).astype(
        np.float32
    )

SEMITONES = 12

def load_audio(path: str) -> tuple[np.ndarray, np.ndarray | None, int, int]:
    data, sample_rate = sf.read(path, dtype="float32")
    if data.ndim == 1:
        return np.ascontiguousarray(data, dtype=np.float32), None, sample_rate, 1
    left = np.ascontiguousarray(data[:, 0], dtype=np.float32)
    right = np.ascontiguousarray(data[:, 1], dtype=np.float32)
    return left, right, sample_rate, 2


class StretchedSource:
    def __init__(
        self,
        sample_rate: int,
        channels: int,
        ratio: float,
        source_callback: "callable",
    ):
        self.channels = channels
        self.source_callback = source_callback

        opts = (
            rubberband.OPTION_PROCESS_REALTIME
            | rubberband.OPTION_ENGINE_FINER
            | rubberband.OPTION_CHANNELS_APART
        )

        self.st_left = rubberband.RealTimeStretcher(
            sample_rate, 1, opts, time_ratio=ratio, pitch_scale=1.0
        )
        self.st_right = (
            rubberband.RealTimeStretcher(
                sample_rate, 1, opts, time_ratio=ratio, pitch_scale=1.0
            )
            if channels == 2
            else None
        )

        pad = np.zeros(self.st_left.get_preferred_start_pad(), dtype=np.float32)
        self.st_left.process(pad, final=False)
        if self.st_right is not None:
            self.st_right.process(pad, final=False)

        self.delay_remaining = self.st_left.get_start_delay()
        self.finished = False

    def pull(self, n_frames: int) -> tuple[np.ndarray, bool]:
        need = n_frames * self.channels
        out_chunks = []
        got = 0

        while got < need:
            av_left = self.st_left.available()
            av_right = self.st_right.available() if self.st_right else av_left

            if av_left == -1 and (self.st_right is None or av_right == -1):
                self.finished = True
                break

            if av_left > 0 and (self.st_right is None or av_right > 0):
                to_take = min(av_left, (need - got) // self.channels)
                if self.st_right is not None:
                    to_take = min(to_take, av_right)
                to_take = max(1, to_take)

                chunk_left = self.st_left.retrieve(to_take)
                chunk_right = self.st_right.retrieve(to_take) if self.st_right else None

                if self.delay_remaining > 0:
                    drop = min(self.delay_remaining, len(chunk_left))
                    if drop > 0:
                        chunk_left = chunk_left[drop:]
                        if chunk_right is not None:
                            chunk_right = chunk_right[drop:]
                        self.delay_remaining -= drop

                if len(chunk_left) > 0:
                    if chunk_right is not None:
                        out = np.column_stack((chunk_left, chunk_right)).flatten()
                    else:
                        out = chunk_left
                    out_chunks.append(out)
                    got += len(out)
                continue

            required = self.st_left.get_samples_required()
            if required <= 0:
                break

            left_chunk, right_chunk = self.source_callback(required)
            if left_chunk is None:
                silence = np.zeros(required, dtype=np.float32)
                self.st_left.process(silence, final=True)
                if self.st_right is not None:
                    self.st_right.process(silence, final=True)
                continue

            n = len(left_chunk)
            final = n < required
            if final:
                pad_len = required - n
                left_chunk = np.concatenate(
                    [left_chunk, np.zeros(pad_len, dtype=np.float32)]
                )
                if right_chunk is not None:
                    right_chunk = np.concatenate(
                        [right_chunk, np.zeros(pad_len, dtype=np.float32)]
                    )

            left_chunk = np.ascontiguousarray(left_chunk, dtype=np.float32)
            self.st_left.process(left_chunk, final=final)
            if self.st_right is not None:
                right_chunk = np.ascontiguousarray(right_chunk, dtype=np.float32)
                self.st_right.process(right_chunk, final=final)

        if not out_chunks:
            out = np.array([], dtype=np.float32)
        else:
            out = np.concatenate(out_chunks).astype(np.float32)

        return out, self.finished


class ResampleBuffer:
    def __init__(
        self,
        stretched_source: StretchedSource,
        channels: int,
        pitch_ratio: float,
    ):
        self.stretched = stretched_source
        self.channels = channels
        self.pitch_ratio = pitch_ratio
        self.buffer = np.array([], dtype=np.float32)
        self.finished = False

    def pull(self, n_frames: int) -> tuple[np.ndarray, bool]:
        need_stretched = int(np.ceil(n_frames * self.pitch_ratio)) * self.channels

        while len(self.buffer) < need_stretched and not self.finished:
            pull_count = max(need_stretched - len(self.buffer), 4096)
            chunk, self.finished = self.stretched.pull(
                pull_count // self.channels
            )
            if len(chunk) > 0:
                self.buffer = np.concatenate([self.buffer, chunk])

        if len(self.buffer) < need_stretched:
            available = len(self.buffer) // self.channels
            if available == 0:
                return np.array([], dtype=np.float32), self.finished
            # Tail: resample available frames to available/pitch_ratio output frames
            n_out = max(0, int(available / self.pitch_ratio))
            if n_out == 0:
                return np.array([], dtype=np.float32), self.finished
            take_stretched = available * self.channels
        else:
            n_out = n_frames
            take_stretched = (need_stretched // self.channels) * self.channels

        stretch_chunk = self.buffer[:take_stretched].copy()
        self.buffer = self.buffer[take_stretched:]

        if self.channels == 1:
            resampled = _resample(stretch_chunk, n_out)
        else:
            left = stretch_chunk[0::2]
            right = stretch_chunk[1::2]
            left_out = _resample(left, n_out)
            right_out = _resample(right, n_out)
            resampled = np.column_stack((left_out, right_out)).flatten()

        return resampled, self.finished


def main():
    ratio = 2 ** (SEMITONES / 12.0)

    print(f"Loading file...")
    left, right, sample_rate, channels = load_audio("rubberband_exp/gravity.mp3")
    n_frames = len(left)
    print(f"  {n_frames} frames, {channels} ch, {sample_rate} Hz")
    print(f"  Duration: {n_frames / sample_rate:.2f} s")
    print(f"  Pitch shift: {SEMITONES:+.1f} semitones (ratio {ratio:.3f})")

    src_pos = [0]

    def source_callback(n: int):
        pos = src_pos[0]
        if pos >= n_frames:
            return None, None
        take = min(n, n_frames - pos)
        l = np.ascontiguousarray(left[pos : pos + take], dtype=np.float32)
        r = (
            np.ascontiguousarray(right[pos : pos + take], dtype=np.float32)
            if right is not None
            else None
        )
        src_pos[0] += take
        return l, r

    stretched = StretchedSource(
        sample_rate, channels, ratio, source_callback
    )
    resampled = ResampleBuffer(stretched, channels, ratio)

    bytes_per_frame = channels * 4

    def stream_callback(in_data, frame_count, time_info, status):
        expected_bytes = frame_count * bytes_per_frame
        out, done = resampled.pull(frame_count)
        buf = out.tobytes()
        if len(buf) < expected_bytes:
            buf = buf + b"\x00" * (expected_bytes - len(buf))
        flag = pyaudio.paComplete if done else pyaudio.paContinue
        return (buf[:expected_bytes], flag)

    pa = pyaudio.PyAudio()
    stream = pa.open(
        format=FORMAT,
        channels=channels,
        rate=sample_rate,
        output=True,
        frames_per_buffer=1024,
        stream_callback=stream_callback,
    )

    print("Playing... (Ctrl+C to stop)")

    try:
        while stream.is_active():
            time.sleep(0.1)
    except KeyboardInterrupt:
        pass
    finally:
        stream.stop_stream()
        stream.close()
        pa.terminate()
    print("Done.")


if __name__ == "__main__":
    main()
