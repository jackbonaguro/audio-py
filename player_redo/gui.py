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
from waveFormSection import WaveformWidget
from playbackSection import PlaybackSection

class MainWindow(QMainWindow):
	def __init__(self, engine=None):
		super().__init__()

		# Set engine for dispatching calls
		self.engine = engine

		# Window meta
		self.setWindowTitle("Stream Progress")
		self.setMinimumWidth(400)

		# Layout
		self.layout = QVBoxLayout()
		self.layout.setSpacing(12)

		# File section
		file_layout = FileLayout()
		self.layout.addLayout(file_layout)

		# Waveform section
		self.waveformWidget = None

		# Playback section
		self.playback_section = PlaybackSection(engine=self.engine)
		self.layout.addLayout(self.playback_section)

		# Set central widget, to display
		central = QWidget()
		central.setLayout(self.layout)
		self.setCentralWidget(central)

	def load_file(self, path: Path):
		self.engine.load_file(path)

	def on_file_loaded(self):
		track = self.engine.get_track()
		if track is None:
			return
		if self.waveformWidget is not None:
			self.layout.removeWidget(self.waveformWidget)
			self.waveformWidget.deleteLater()
		self.waveformWidget = WaveformWidget()
		self.waveformWidget.set_audio(track.buffer)
		self.layout.addWidget(self.waveformWidget)

		# Enable playback section
		self.playback_section.set_enabled(True)
