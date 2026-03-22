from PySide6.QtWidgets import QHBoxLayout, QPushButton, QSlider, QVBoxLayout
from PySide6.QtCore import Qt

from commandUtil import CommandUtil
from waveFormSection import WaveformWidget

SLIDER_MAX = 10000

class PlaybackSection(QVBoxLayout):
	def __init__(self, command_util: CommandUtil):
		super().__init__()

		self.playing = False

		self.command_util = command_util
		self._duration = 0.0
		self._updating_from_rt = False
		self._user_dragging = False

		self.position_slider = QSlider(Qt.Orientation.Horizontal)
		self.position_slider.setRange(0, SLIDER_MAX)
		self.position_slider.setValue(0)
		self.position_slider.sliderPressed.connect(lambda: setattr(self, "_user_dragging", True))
		self.position_slider.sliderReleased.connect(self._on_slider_released)
		self.addWidget(self.position_slider)

		btn_row = QHBoxLayout()
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
		self.position_slider.setEnabled(enabled)
		self.waveform_widget.setEnabled(enabled)

	def set_duration(self, duration: float):
		self._duration = max(0, duration)
		self.waveform_widget.set_duration(duration)

	def _send_seek(self, value: int):
		if self._duration <= 0:
			return
		pos = (value / SLIDER_MAX) * self._duration
		self.command_util.send_command({"command": "seek", "position": pos})

	def _on_waveform_seek(self, position: float):
		self._user_dragging = True
		if self._duration <= 0:
			return
		pos = max(0.0, min(self._duration, position))
		self.command_util.send_command({"command": "seek", "position": pos})
		# Update slider and waveform immediately for responsive feedback
		val = int(SLIDER_MAX * pos / self._duration)
		self.position_slider.setValue(min(val, SLIDER_MAX))
		self.waveform_widget.update_position(pos)

	def _on_waveform_seek_finished(self):
		self._user_dragging = False

	def update_position(self, position: float):
		"""Update slider from RT process position status (no seek command)."""
		if self._user_dragging:
			return
		self._updating_from_rt = True
		if self._duration > 0:
			val = int(SLIDER_MAX * position / self._duration)
			self.position_slider.setValue(min(val, SLIDER_MAX))
			self.waveform_widget.update_position(position)
		self._updating_from_rt = False

	def _on_slider_released(self):
		self._user_dragging = False
		if self._updating_from_rt:
			return
		pos = (self.position_slider.value() / SLIDER_MAX) * self._duration
		self._send_seek(self.position_slider.value())
		self.waveform_widget.update_position(pos)

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
