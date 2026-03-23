import numpy as np
import librosa

class TempoDetector:
	def detect(self, audio_data: np.ndarray) -> float:
		tempo, beats = librosa.beat.beat_track(y=audio_data, sr=44100)
		return float(np.atleast_1d(tempo)[0])
