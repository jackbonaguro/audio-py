"""State container for the main (GUI) process."""


class AppState:
	def __init__(self):
		# Track number (0-based) of the main track
		self.main_track: int | None = None
		# Playback tempo (BPM) of the main track; original tempo * speed ratio
		self.main_tempo: float | None = None
		# Track IDs that are synced to the main tempo
		self.synced_tracks: set[int] = set()
