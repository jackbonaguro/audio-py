from PySide6.QtGui import QFont
from PySide6.QtWidgets import QHBoxLayout, QPushButton, QSlider, QVBoxLayout, QLabel
from PySide6.QtCore import Qt

from commandUtil import CommandUtil
from waveFormSection import WaveformWidget

class PlaybackSection(QVBoxLayout):
	def __init__(self, command_util: CommandUtil):
		super().__init__()

		self.playing = False

		self.command_util = command_util
		self._duration = 0.0
		self._updating_from_rt = False
		self._user_dragging = False

		btn_row = QHBoxLayout()

		# Logarithmic playback speed adjust slider
		self.adjust_lower_label = QLabel("0.5")
		self.adjust_upper_label = QLabel("2.0")
		self.speed_value_label = QLabel("(1.0)")
		font = QFont()
		font.setStyleHint(QFont.StyleHint.Monospace)
		font.setFixedPitch(True)
		self.speed_value_label.setFont(font)
		self.adjust_speed_slider = QSlider(Qt.Orientation.Horizontal)
		self.adjust_speed_slider.setRange(-100, 100)
		self.adjust_speed_slider.setValue(0)
		self.adjust_speed_slider.valueChanged.connect(self.set_speed)
		self.adjust_speed_slider.setTickPosition(QSlider.TickPosition.TicksBelow)
		self.adjust_speed_slider.setTickInterval(10)

		btn_row.addWidget(self.adjust_lower_label)
		btn_row.addWidget(self.adjust_speed_slider)
		btn_row.addWidget(self.speed_value_label)
		btn_row.addWidget(self.adjust_upper_label)

		self.play_btn = QPushButton("▶️")
		self.play_btn.clicked.connect(self.play)
		self.play_btn.setEnabled(False)
		btn_row.addWidget(self.play_btn)

		self.stop_btn = QPushButton("⏹️")
		self.stop_btn.clicked.connect(self.stop)
		self.stop_btn.setEnabled(False)
		btn_row.addWidget(self.stop_btn)

		self.addLayout(btn_row)

		# Waveform section
		self.waveform_widget = WaveformWidget()
		self.waveform_widget.seek_requested.connect(self._on_waveform_seek)
		self.waveform_widget.seek_finished.connect(self._on_waveform_seek_finished)
		self.addWidget(self.waveform_widget)

	def on_waveform_ready(self, status):
		if self.waveform_widget is None:
			self.waveform_widget = WaveformWidget()
			self.insertWidget(1, self.waveformWidget)
		waveform = status.get("waveform")
		self.waveform_widget.set_waveform_data(waveform)

		if status.get("duration") is not None:
			self.set_duration(status["duration"])
		self.set_enabled(True)

	def set_enabled(self, enabled: bool):
		self.play_btn.setEnabled(enabled)
		# self.position_slider.setEnabled(enabled)
		self.waveform_widget.setEnabled(enabled)

	def set_duration(self, duration: float):
		self._duration = max(0, duration)
		self.waveform_widget.set_duration(duration)

	def _on_waveform_seek(self, position: float):
		self._user_dragging = True
		if self._duration <= 0:
			return
		pos = max(0.0, min(self._duration, position))
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
		if self._duration > 0:
			self.waveform_widget.update_position(position)
		self._updating_from_rt = False

	def play(self):
		if not self.playing:
			self.playing = True
			self.command_util.send_command({"command": "play"})
			self.stop_btn.setEnabled(True)
			self.play_btn.setText("⏸️")
		else:
			self.playing = False
			self.command_util.send_command({"command": "pause"})
			self.play_btn.setEnabled(True)
			self.stop_btn.setEnabled(True)
			self.play_btn.setText("▶️")

	def stop(self):
		self.command_util.send_command({"command": "stop"})
		self.play_btn.setEnabled(True)
		self.stop_btn.setEnabled(False)

	def on_track_stopped(self):
		self.playing = False
		self.play_btn.setEnabled(True)
		self.stop_btn.setEnabled(False)
		self.play_btn.setText("▶️")
		self.waveform_widget.update_position(0)

	def set_speed(self, value: int):
		# Convert integer slider (-100..100) to float -1..1, then to log range 0.5..2.0
		# 2^x maps (-1, 0, 1) -> (0.5, 1.0, 2.0)
		x = value / 100.0
		speed = 2 ** x
		self.speed_value_label.setText(f"({speed:.1f})")
		self.command_util.send_command({"command": "set_speed", "speed": speed})
