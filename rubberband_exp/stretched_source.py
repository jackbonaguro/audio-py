import numpy as np
import rubberband

from audio_source import AudioSource


class StretchedSource:
    """Mono only. For stereo, create two instances and interleave pulls."""

    def __init__(
        self,
        sample_rate: int,
        ratio: float,
        source: AudioSource,
    ):
        self.source = source

        opts = (
            rubberband.OPTION_PROCESS_REALTIME
            | rubberband.OPTION_ENGINE_FINER
        )

        self.st = rubberband.RealTimeStretcher(
            sample_rate, 1, opts, time_ratio=ratio, pitch_scale=1.0
        )

        # Feed start padding
        pad = np.zeros(self.st.get_preferred_start_pad(), dtype=np.float32)
        self.st.process(pad, final=False)

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
