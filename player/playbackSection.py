from PySide6.QtWidgets import QHBoxLayout, QPushButton, QVBoxLayout, QLabel
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QFontDatabase, QFontMetrics

from commandUtil import CommandUtil
from speedPitchSection import SpeedPitchSection
from waveFormSection import WaveformWidget


def _format_time(seconds: float) -> str:
	"""Format seconds as m:ss."""
	if seconds < 0 or not (seconds == seconds):  # NaN check
		return "--:--"
	m = int(seconds // 60)
	s = int(seconds % 60)
	return f"{m}:{s:02d}"


class PlaybackSection(QVBoxLayout):
	def __init__(self, command_util: CommandUtil):
		super().__init__()

		self.playing = False

		self.command_util = command_util
		self._duration = 0.0
		self._position = 0.0
		self._updating_from_rt = False
		self._user_dragging = False

		self.speedPitchSection = SpeedPitchSection(command_util)
		self.addLayout(self.speedPitchSection)

		self.play_btn = QPushButton("▶")
		self.play_btn.setFixedWidth(32)
		self.play_btn.clicked.connect(self.play)
		self.play_btn.setEnabled(False)
		self.stop_btn = QPushButton("⏹")
		self.stop_btn.setFixedWidth(32)
		self.stop_btn.clicked.connect(self.stop)
		self.stop_btn.setEnabled(False)

		# Waveform section
		self.waveform_widget = WaveformWidget()
		self.waveform_widget.seek_requested.connect(self._on_waveform_seek)
		self.waveform_widget.seek_finished.connect(self._on_waveform_seek_finished)
		self.addWidget(self.waveform_widget)

		# Bottom status row: time (position), duration
		mono = QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)
		mono.setFixedPitch(True)
		status_row = QHBoxLayout()
		# Fixed widths to prevent layout shift when track loads (must accommodate placeholders)
		fm = QFontMetrics(mono)
		time_w = max(fm.horizontalAdvance("--:--"), fm.horizontalAdvance("99:59")) + 1 # IDK why but without this layout shifts
		self.time_label = QLabel("--:--")
		self.time_label.setFont(mono)
		self.time_label.setMinimumWidth(time_w)
		self.duration_label = QLabel("--:--")
		self.duration_label.setFont(mono)
		self.duration_label.setMinimumWidth(time_w)

		status_row.addWidget(QLabel("Time"))
		status_row.addWidget(self.time_label)
		status_row.addSpacing(16)
		status_row.addWidget(QLabel("Duration"))
		status_row.addWidget(self.duration_label)
		status_row.addSpacing(16)
		status_row.addStretch()
		status_row.addWidget(self.play_btn)
		status_row.addWidget(self.stop_btn)
		self.addLayout(status_row)

	def on_waveform_ready(self, status):
		if self.waveform_widget is None:
			self.waveform_widget = WaveformWidget()
			self.insertWidget(1, self.waveform_widget)
		waveform = status.get("waveform")
		self.waveform_widget.set_waveform_data(waveform)

		if status.get("tempo") is not None:
			self.set_tempo(status.get("tempo"))

		if status.get("duration") is not None:
			self.set_duration(status.get("duration"))
		self.set_enabled(True)

	def set_enabled(self, enabled: bool):
		self.play_btn.setEnabled(enabled)
		# self.position_slider.setEnabled(enabled)
		self.waveform_widget.setEnabled(enabled)

	def set_duration(self, duration: float):
		self._duration = max(0, duration)
		self.waveform_widget.set_duration(duration)
		self.duration_label.setText(_format_time(self._duration))

	def set_tempo(self, tempo: float):
		self.speedPitchSection.set_tempo(tempo)

	def _on_waveform_seek(self, position: float):
		self._user_dragging = True
		if self._duration <= 0:
			return
		pos = max(0.0, min(self._duration, position))
		self._position = pos
		self.time_label.setText(_format_time(pos))
		self.command_util.send_command({"command": "seek", "position": pos})
		# Update waveform immediately for responsive feedback
		self.waveform_widget.update_position(pos)

	def _on_waveform_seek_finished(self):
		self._user_dragging = False

	def update_position(self, position: float):
		"""Update slider from RT process position status (no seek command)."""
		if self._user_dragging:
			return
		self._updating_from_rt = True
		self._position = position
		self.time_label.setText(_format_time(position))
		if self._duration > 0:
			self.waveform_widget.update_position(position)
		self._updating_from_rt = False

	def play(self):
		if not self.playing:
			self.playing = True
			self.command_util.send_command({"command": "play"})
			self.stop_btn.setEnabled(True)
			self.play_btn.setText("⏸")
		else:
			self.playing = False
			self.command_util.send_command({"command": "pause"})
			self.play_btn.setEnabled(True)
			self.stop_btn.setEnabled(True)
			self.play_btn.setText("▶")

	def stop(self):
		self.command_util.send_command({"command": "stop"})
		self.play_btn.setEnabled(True)
		self.stop_btn.setEnabled(False)

	def on_track_stopped(self):
		self.playing = False
		self.play_btn.setEnabled(True)
		self.stop_btn.setEnabled(False)
		self.play_btn.setText("▶")
		self._position = 0.0
		self.time_label.setText(_format_time(0))
		self.waveform_widget.update_position(0)
