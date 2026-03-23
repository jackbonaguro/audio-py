import time
import numpy as np
import pyaudio
import soundfile as sf

from raw_data_source import RawDataSource
from resample_source import ResampleSource
from stretched_source import StretchedSource

FORMAT = pyaudio.paFloat32

SEMITONES = 12


def load_audio(path: str) -> tuple[np.ndarray, np.ndarray | None, int, int]:
    data, sample_rate = sf.read(path, dtype="float32")
    if data.ndim == 1:
        return np.ascontiguousarray(data, dtype=np.float32), None, sample_rate, 1
    left = np.ascontiguousarray(data[:, 0], dtype=np.float32)
    right = np.ascontiguousarray(data[:, 1], dtype=np.float32)
    return left, right, sample_rate, 2


def main():
    ratio = 2 ** (SEMITONES / 12.0)

    print(f"Loading file...")
    left, right, sample_rate, channels = load_audio("rubberband_exp/gravity.mp3")
    n_frames = len(left)
    print(f"  {n_frames} frames, {channels} ch, {sample_rate} Hz")
    print(f"  Duration: {n_frames / sample_rate:.2f} s")
    print(f"  Pitch shift: {SEMITONES:+.1f} semitones (ratio {ratio:.3f})")

    def make_chain(chan: np.ndarray):
        raw = RawDataSource(chan)
        stretched = StretchedSource(sample_rate, ratio, raw)
        return ResampleSource(stretched, ratio)

    if right is not None:
        # Stereo: two mono chains (RawDataSource -> StretchedSource -> ResampleSource each)
        resampled_l = make_chain(left)
        resampled_r = make_chain(right)

        def pull_stereo(n: int):
            l_out, done_l = resampled_l.pull(n)
            r_out, done_r = resampled_r.pull(n)
            n_out = min(len(l_out), len(r_out))
            if n_out == 0:
                return np.array([], dtype=np.float32), done_l and done_r
            out = np.column_stack((l_out[:n_out], r_out[:n_out])).flatten()
            return out, done_l and done_r

        pull_fn = pull_stereo
    else:
        resampled = make_chain(left)

        def pull_fn(n: int):
            return resampled.pull(n)

    bytes_per_frame = channels * 4

    def stream_callback(in_data, frame_count, time_info, status):
        expected_bytes = frame_count * bytes_per_frame
        out, done = pull_fn(frame_count)
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
