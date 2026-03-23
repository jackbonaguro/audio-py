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
)

from pathlib import Path
import numpy as np
from fileSection import FileLayout
from loadWorker import LoadWorker
from waveFormSection import WaveformWidget
from playbackSection import PlaybackSection

from commandUtil import CommandUtil

class MainWindow(QMainWindow):
	def __init__(self, command_util: CommandUtil):
		super().__init__()

		# Set engine for dispatching calls
		self.command_util = command_util
		self._load_worker: LoadWorker | None = None

		# Window meta
		self.setWindowTitle("Jack's Mixer")
		self.setMinimumWidth(800)

		# Layout
		self.layout = QVBoxLayout()
		self.layout.setSpacing(12)

		# File section
		self.file_layout = FileLayout()
		self.layout.addLayout(self.file_layout)

		# Playback section
		self.playback_section = PlaybackSection(command_util=self.command_util)
		self.layout.addLayout(self.playback_section)

		# Set central widget, to display
		central = QWidget()
		central.setLayout(self.layout)
		self.setCentralWidget(central)

	def load_file(self, path: Path):
		# self.command_util.send_command({"command": "load_file", "path": str(path)})
		if self._load_worker is not None and self._load_worker.isRunning():
			return
		self._load_worker = LoadWorker(path, self.command_util)
		self._load_worker.error.connect(self._on_load_error)
		self._load_worker.start()

	def _on_load_error(self, msg: str):
		print(f"Load error: {msg}")

	def on_waveform_ready(self, status):
		"""Called when RT process sends precomputed waveform (multiprocess flow)."""
		waveform = status.get("waveform")
		if waveform is None:
			return
		self.playback_section.on_waveform_ready(status)

	def on_position_received(self, position: float):
		"""Handle position and other status updates from RT process."""
		self.playback_section.update_position(position)

	def on_track_stopped(self):
		self.playback_section.on_track_stopped()

	def on_load_progress(self, progress: float):
		self.file_layout.update_progress(progress)
