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

		# Tempo label
		self.tempo_label = QLabel("Tempo: ")
		self.tempo_value_label = QLabel("--")
		btn_row.addWidget(self.tempo_label)
		btn_row.addWidget(self.tempo_value_label)

		# Logarithmic playback speed adjust slider
		self.speed_label = QLabel("Speed")
		self.speed_slider = QSlider(Qt.Orientation.Horizontal)
		self.speed_slider.setRange(-100, 100)
		self.speed_slider.setValue(0)
		self.speed_slider.valueChanged.connect(self.set_speed)
		self.speed_slider.setTickPosition(QSlider.TickPosition.TicksBelow)
		self.speed_slider.setTickInterval(10)
		btn_row.addWidget(self.speed_label)
		btn_row.addWidget(self.speed_slider)

		# Pitch adjust slider
		self.pitch_label = QLabel("Pitch")
		self.pitch_slider = QSlider(Qt.Orientation.Horizontal)
		self.pitch_slider.setRange(-12, 12)
		self.pitch_slider.setValue(0)
		self.pitch_slider.valueChanged.connect(self.set_pitch)
		self.pitch_slider.setTickPosition(QSlider.TickPosition.TicksBelow)
		self.pitch_slider.setTickInterval(1)
		btn_row.addWidget(self.pitch_label)
		btn_row.addWidget(self.pitch_slider)

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

	def set_tempo(self, tempo: float):
		self.tempo = tempo
		print(f"Tempo: {tempo}")
		self.tempo_value_label.setText(f"{tempo:.1f}")

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
		self.command_util.send_command({"command": "set_speed", "speed": speed})

	def set_pitch(self, value: int):
		self.command_util.send_command({"command": "set_pitch", "pitch": value})
