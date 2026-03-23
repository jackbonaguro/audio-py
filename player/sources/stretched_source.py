import numpy as np
import rubberband

from .audio_source import AudioSource


def semitones_to_pitch_scale(semitones: float) -> float:
    """Convert semitones to Rubber Band pitch scale. 0 -> 1.0, 12 -> 2.0 (one octave up)."""
    return 2.0 ** (semitones / 12.0)


class StretchedSource:
    """
    Mono only. For stereo, create two instances and interleave pulls.
    Uses Rubber Band's native pitch scaling for real-time safe pitch/speed changes.
    """

    def __init__(
        self,
        sample_rate: int,
        time_ratio: float = 1.0,
        pitch_scale: float = 1.0,
        source: AudioSource | None = None,
    ):
        self.source = source
        self.sample_rate = sample_rate
        self.time_ratio = time_ratio
        self.pitch_scale = pitch_scale

        opts = (
            rubberband.OPTION_PROCESS_REALTIME
            | rubberband.OPTION_ENGINE_FINER
            | rubberband.OPTION_FORMANT_PRESERVED
        )
        self._opts = opts

        self._init_stretcher()
        self.delay_remaining = self.st.get_start_delay()
        self.finished = False

    def _init_stretcher(self):
        self.st = rubberband.RealTimeStretcher(
            self.sample_rate,
            1,
            self._opts,
            time_ratio=self.time_ratio,
            pitch_scale=self.pitch_scale,
        )
        pad = np.zeros(self.st.get_preferred_start_pad(), dtype=np.float32)
        self.st.process(pad, final=False)

    def set_time_ratio(self, time_ratio: float):
        """Update playback speed. Real-time safe; does not reset buffers."""
        self.time_ratio = time_ratio
        self.st.set_time_ratio(time_ratio)

    def set_pitch_scale(self, pitch_scale: float):
        """Update pitch. Real-time safe; does not reset buffers."""
        self.pitch_scale = pitch_scale
        self.st.set_pitch_scale(pitch_scale)

    def set_pitch_semitones(self, semitones: float):
        """Update pitch in semitones. 0 = no change, 12 = one octave up."""
        self.set_pitch_scale(semitones_to_pitch_scale(semitones))

    def seek(self, pos: int):
        """Seek to frame position. Resets stretcher and seeks underlying source."""
        self.source.seek(pos)
        self._init_stretcher()
        self.delay_remaining = self.st.get_start_delay()
        self.finished = False

    def pull(self, n_frames: int) -> tuple[np.ndarray, bool]:
        out_chunks = []
        got = 0

        while got < n_frames:
            av = self.st.available()

            if av == -1:
                self.finished = True
                break

            if av > 0:
                to_take = min(av, n_frames - got)
                to_take = max(1, to_take)

                chunk = self.st.retrieve(to_take)

                if self.delay_remaining > 0:
                    drop = min(self.delay_remaining, len(chunk))
                    if drop > 0:
                        chunk = chunk[drop:]
                        self.delay_remaining -= drop

                if len(chunk) > 0:
                    out_chunks.append(chunk)
                    got += len(chunk)
                continue

            required = self.st.get_samples_required()
            if required <= 0:
                break

            chunk, finished = self.source.pull(required)
            if finished and len(chunk) == 0:
                silence = np.zeros(required, dtype=np.float32)
                self.st.process(silence, final=True)
                continue

            n = len(chunk)
            final = finished or n < required
            if final:
                chunk = np.concatenate(
                    [chunk, np.zeros(required - n, dtype=np.float32)]
                )

            chunk = np.ascontiguousarray(chunk, dtype=np.float32)
            self.st.process(chunk, final=final)

        if not out_chunks:
            out = np.array([], dtype=np.float32)
        else:
            out = np.concatenate(out_chunks).astype(np.float32)

        return out, self.finished
