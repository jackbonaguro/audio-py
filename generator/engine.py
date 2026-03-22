import pyaudio
import numpy as np

SAMPLE_RATE = 44100
CHUNK = 1024
CHANNELS = 2

# Base class, square wave
class PlayingNote:
    def __init__(self, frequency: float):
        self.frequency = frequency
        self.phase = 0.0

    def generate_mono(self, phases: np.ndarray) -> np.ndarray:
      return np.sign(np.sin(phases)).astype(np.float32)

    def generate_stereo(self, phases: np.ndarray) -> np.ndarray:
      mono = self.generate_mono(phases)
      return np.column_stack((mono, mono))

    def generate_chunk(self, frame_count: int) -> np.ndarray:
        omega = 2 * np.pi * self.frequency / SAMPLE_RATE
        phases = self.phase + omega * np.arange(frame_count)
        stereo = self.generate_stereo(phases)
        self.phase = (phases[-1] + omega) % (2 * np.pi)
        return stereo

class PlayingNoteSine(PlayingNote):
    def generate_mono(self, phases: np.ndarray) -> np.ndarray:
        return np.sin(phases).astype(np.float32)

class PlayingNoteSawtooth(PlayingNote):
    def generate_mono(self, phases: np.ndarray) -> np.ndarray:
        # Sawtooth: ramp from -1 to 1 over one period (phase 0 → 2π)
        phases_mod = phases % (2 * np.pi)
        return (2 * phases_mod / (2 * np.pi) - 1).astype(np.float32)

class PlayingNoteCompound(PlayingNote):
    """A compound generator with square on the left and saw on the right"""

    def __init__(self, frequency: float):
        super().__init__(frequency)
        self.square = PlayingNote(frequency)
        self.sawtooth = PlayingNoteSawtooth(frequency)

    def generate_stereo(self, phases: np.ndarray) -> np.ndarray:
        square = self.square.generate_mono(phases)
        sawtooth = self.sawtooth.generate_mono(phases)
        return np.column_stack((square, sawtooth))

class PlayingNoteHarmonics(PlayingNote):
    """A compound generator with multiple harmonics of sine waves.
    Each harmonic n uses frequency n * fundamental and phase n * fundamental_phase."""

    def __init__(self, frequency: float, num_harmonics: int = 10):
        super().__init__(frequency)
        self.num_harmonics = num_harmonics

    def generate_mono(self, phases: np.ndarray) -> np.ndarray:
        # Harmonic n has freq = (n+1)*fundamental, needs phase = (n+1)*fundamental_phase
        result = np.zeros(len(phases), dtype=np.float32)
        for n in range(1, self.num_harmonics + 1):
            result += np.sin(phases * n).astype(np.float32) / n
        return result
        

class AudioEngine:
    def __init__(self):
        self._notes: dict[float, PlayingNote] = {}
        self.p = pyaudio.PyAudio()
        self.stream = self.p.open(
            format=pyaudio.paFloat32,
            channels=CHANNELS,
            rate=SAMPLE_RATE,
            output=True,
            frames_per_buffer=CHUNK,
            stream_callback=self._stream_callback,
        )

    def _stream_callback(self, in_data, frame_count, time_info, status):
        """Called by PyAudio when it needs more samples."""
        stereo = np.zeros((frame_count, 2), dtype=np.float32)
        notes = list(self._notes.values())
        for note in notes:
            stereo += note.generate_chunk(frame_count)
        n = len(notes)
        if n > 0:
            stereo /= n
        return (stereo.astype(np.float32).tobytes(), pyaudio.paContinue)

    def play_note(self, frequency: float):
        if frequency not in self._notes:
            self._notes[frequency] = PlayingNoteHarmonics(frequency)

    def stop_note(self, frequency: float):
        self._notes.pop(frequency, None)
