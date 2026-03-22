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

from commandUtil import CommandUtil

class MainWindow(QMainWindow):
	def __init__(self, command_util: CommandUtil):
		super().__init__()

		# Set engine for dispatching calls
		self.command_util = command_util

		# Window meta
		self.setWindowTitle("Stream Progress")
		self.setMinimumWidth(400)

		# Layout
		self.layout = QVBoxLayout()
		self.layout.setSpacing(12)

		# File section
		file_layout = FileLayout()
		self.layout.addLayout(file_layout)

		# Waveform section (created when we receive waveform from RT process)
		self.waveformWidget = None

		# Playback section
		self.playback_section = PlaybackSection(command_util=self.command_util)
		self.layout.addLayout(self.playback_section)

		# Set central widget, to display
		central = QWidget()
		central.setLayout(self.layout)
		self.setCentralWidget(central)

	def load_file(self, path: Path):
		self.command_util.send_command({"command": "load_file", "path": str(path)})

	def on_waveform_ready(self, waveform):
		"""Called when RT process sends precomputed waveform (multiprocess flow)."""
		if self.waveformWidget is None:
			self.waveformWidget = WaveformWidget()
			self.layout.insertWidget(1, self.waveformWidget)
		self.waveformWidget.set_waveform_data(waveform)
		self.playback_section.set_enabled(True)
