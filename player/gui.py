from PySide6.QtWidgets import (
	QApplication,
	QMainWindow,
	QWidget,
	QVBoxLayout,
	QHBoxLayout,
	QProgressBar,
	QSlider,
	QLabel,
	QPushButton,
	QFileDialog,
	QLineEdit,
	QFrame,
	QSpacerItem,
	QSizePolicy,
)

from pathlib import Path

from appState import AppState
from components import FileLayout, LabelValuePair, TrackComponent
from loadWorker import LoadWorker

from commandUtil import CommandUtil

class MainWindow(QMainWindow):
	def __init__(self, command_util: CommandUtil):
		super().__init__()

		# Set engine for dispatching calls
		self.command_util = command_util
		self.app_state = AppState()
		self._load_worker: LoadWorker | None = None

		# Window meta
		self.setWindowTitle("Jack's Mixer")
		self.setMinimumWidth(800)

		# Layout
		self.layout = QVBoxLayout()
		self.layout.setSpacing(12)

		# Main track label
		main_track_row = QHBoxLayout()
		self.main_track_pair = LabelValuePair("Main track: ", ["--", "A", "B"])
		self.main_tempo_pair = LabelValuePair(
			"Tempo: ", ["---.-", "999.9"],
			tooltip="Main track playback tempo",
		)
		main_track_row.addWidget(self.main_track_pair)
		main_track_row.addWidget(self.main_tempo_pair)
		main_track_row.addStretch()
		self.layout.addLayout(main_track_row)

		# File section
		self.file_layout = FileLayout()
		self.layout.addLayout(self.file_layout)

		# Tracks 1 & 2 side by side (left & right)
		self.tracks = [
			TrackComponent(
				track_id=0,
				command_util=self.command_util,
				app_state=self.app_state,
				on_main_track_changed=self._on_main_track_changed,
				on_main_tempo_changed=self._on_main_tempo_changed,
				on_sync_changed=self._on_sync_changed,
			),
			TrackComponent(
				track_id=1,
				command_util=self.command_util,
				app_state=self.app_state,
				on_main_track_changed=self._on_main_track_changed,
				on_main_tempo_changed=self._on_main_tempo_changed,
				on_sync_changed=self._on_sync_changed,
			),
		]
		tracks_row = QHBoxLayout()
		tracks_row.setSpacing(12)
		track1_col = QVBoxLayout()
		track1_col.addWidget(QLabel("A"))
		track1_col.addLayout(self.tracks[0])
		tracks_row.addLayout(track1_col)

		spacer = QSpacerItem(100, 0, QSizePolicy.Minimum, QSizePolicy.Minimum)
		tracks_row.addSpacerItem(spacer)

		track2_col = QVBoxLayout()
		track2_col.addWidget(QLabel("B"))
		track2_col.addLayout(self.tracks[1])
		tracks_row.addLayout(track2_col)
		self.layout.addLayout(tracks_row)

		# Set central widget, to display
		central = QWidget()
		central.setLayout(self.layout)
		self.setCentralWidget(central)

	def load_file(self, path: Path, track_id: int):
		# self.command_util.send_command({"command": "load_file", "path": str(path)})
		if self._load_worker is not None and self._load_worker.isRunning():
			return
		self._load_worker = LoadWorker(path, self.command_util, track_id)
		self._load_worker.error.connect(self._on_load_error)
		self._load_worker.start()

	def _on_load_error(self, msg: str):
		print(f"Load error: {msg}")

	def _on_main_track_changed(self):
		main = self.app_state.main_track
		if main is None:
			self.main_track_pair.set_text("--")
			self.app_state.main_tempo = None
			self.app_state.synced_tracks.clear()
		else:
			self.main_track_pair.set_text("A" if main == 0 else "B")
			self.app_state.synced_tracks.discard(main)  # Can't sync to self
			track = self.tracks[main]
			self.app_state.main_tempo = track.get_effective_tempo()
		self._update_main_tempo_display()
		self._apply_main_tempo_to_synced_tracks()
		for i, track in enumerate(self.tracks):
			track.set_main_state(self.app_state.main_track == i)
			track.update_sync_state()

	def _on_main_tempo_changed(self):
		self.app_state.main_tempo = (
			self.tracks[self.app_state.main_track].get_effective_tempo()
			if self.app_state.main_track is not None
			else None
		)
		self._update_main_tempo_display()
		self._apply_main_tempo_to_synced_tracks()
		for track in self.tracks:
			track.update_sync_state()

	def _on_sync_changed(self):
		self._apply_main_tempo_to_synced_tracks()
		for track in self.tracks:
			track.update_sync_state()

	def _apply_main_tempo_to_synced_tracks(self):
		if self.app_state.main_tempo is None:
			return
		for track_id in self.app_state.synced_tracks:
			self.tracks[track_id].set_effective_tempo(self.app_state.main_tempo)

	def _update_main_tempo_display(self):
		if self.app_state.main_tempo is not None:
			self.main_tempo_pair.set_text(f"{self.app_state.main_tempo:03.1f}")
		else:
			self.main_tempo_pair.set_text("---.-")

	def on_waveform_ready(self, status):
		"""Called when RT process sends precomputed waveform (multiprocess flow)."""
		waveform = status.get("waveform")
		if waveform is None:
			return
		track_id = status.get("track_id", 0)
		track = self._get_track(track_id)
		if track:
			track.on_waveform_ready(status)

	def on_position_received(self, status):
		"""Handle position and other status updates from RT process."""
		track_id = status.get("track_id", 0)
		track = self._get_track(track_id)
		if track:
			track.update_position(status.get("position", 0))

	def on_track_stopped(self, status=None):
		track_id = status.get("track_id", 0) if isinstance(status, dict) else 0
		track = self._get_track(track_id)
		if track:
			track.on_track_stopped()

	def _get_track(self, track_id: int):
		"""Return TrackComponent for track_id."""
		if track_id == 0:
			return self.tracks[0]
		if track_id == 1:
			return self.tracks[1]
		return None

	def on_load_progress(self, progress: float):
		self.file_layout.update_progress(progress)
