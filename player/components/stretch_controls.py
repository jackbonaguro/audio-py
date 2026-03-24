from typing import Callable

from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QSlider
from PySide6.QtCore import Qt
from PySide6.QtGui import QFontDatabase, QFontMetrics

from commandUtil import CommandUtil


class StretchControls(QHBoxLayout):
	def __init__(
		self,
		command_util: CommandUtil,
		track_id: int,
		app_state,
		on_main_track_changed: Callable[[], None],
		on_effective_tempo_changed: Callable[[float | None], None] | None = None,
	):
		super().__init__()
		self.command_util = command_util
		self._track_id = track_id
		self._app_state = app_state
		self._on_main_track_changed = on_main_track_changed
		self._on_effective_tempo_changed = on_effective_tempo_changed
		self._original_tempo: float | None = None

		# Logarithmic playback speed adjust slider
		self.speed_reset_btn = QPushButton("Rs")
		self.speed_reset_btn.setEnabled(False)
		self.speed_reset_btn.clicked.connect(self._reset_speed)
		self.speed_slider = QSlider(Qt.Orientation.Horizontal)
		self.speed_slider.setRange(-100, 100)
		self.speed_slider.setValue(0)
		self.speed_slider.setTickInterval(50)
		self.speed_slider.valueChanged.connect(self.set_speed)
		self.speed_slider.valueChanged.connect(self._update_speed_reset_btn)
		self.speed_slider.setTickPosition(QSlider.TickPosition.TicksAbove)
		self.addWidget(self.speed_reset_btn)
		self.addWidget(self.speed_slider)

		# Pitch adjust slider
		self.pitch_reset_btn = QPushButton("Rp")
		self.pitch_reset_btn.setEnabled(False)
		self.pitch_reset_btn.clicked.connect(self._reset_pitch)
		self.pitch_slider = QSlider(Qt.Orientation.Horizontal)
		self.pitch_slider.setRange(-1200, 1200)
		self.pitch_slider.setValue(0)
		self.pitch_slider.setTickInterval(600)
		self.pitch_slider.setTickPosition(QSlider.TickPosition.TicksAbove)
		self.pitch_slider.valueChanged.connect(self.set_pitch)
		self.pitch_slider.valueChanged.connect(self._update_pitch_reset_btn)
		self.addWidget(self.pitch_reset_btn)
		self.addWidget(self.pitch_slider)

		# Main and Sync buttons
		self.main_btn = QPushButton("M")
		self.main_btn.setToolTip("Main")
		self.main_btn.setCheckable(True)
		self.main_btn.clicked.connect(self._on_main_clicked)
		self.sync_btn = QPushButton("Sync")
		self.sync_btn.setToolTip("Sync")
		self.addWidget(self.main_btn)
		self.addWidget(self.sync_btn)

		mono = QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)
		mono.setFixedPitch(True)
		fm = QFontMetrics(mono)
		tempo_w = max(fm.horizontalAdvance("---.-"), fm.horizontalAdvance("999.9")) + 1
		self.tempo_label = QLabel("Tempo: ")
		self.tempo_value_label = QLabel("---.-")
		self.tempo_value_label.setFont(mono)
		self.tempo_value_label.setMinimumWidth(tempo_w)
		self.addWidget(self.tempo_label)
		self.addWidget(self.tempo_value_label)

	SPEED_DEFAULT = 0
	PITCH_DEFAULT = 0

	def _reset_speed(self):
		self.speed_slider.setValue(self.SPEED_DEFAULT)

	def _reset_pitch(self):
		self.pitch_slider.setValue(self.PITCH_DEFAULT)

	def _update_speed_reset_btn(self):
		self.speed_reset_btn.setEnabled(self.speed_slider.value() != self.SPEED_DEFAULT)

	def _update_pitch_reset_btn(self):
		self.pitch_reset_btn.setEnabled(self.pitch_slider.value() != self.PITCH_DEFAULT)

	def _on_main_clicked(self):
		if self._app_state.main_track == self._track_id:
			self._app_state.main_track = None
		else:
			self._app_state.main_track = self._track_id
		self._on_main_track_changed()

	def set_main_state(self, is_main: bool):
		self.main_btn.setChecked(is_main)

	def set_enabled(self, enabled: bool):
		self.speed_reset_btn.setEnabled(enabled and self.speed_slider.value() != self.SPEED_DEFAULT)
		self.speed_slider.setEnabled(enabled)
		self.pitch_reset_btn.setEnabled(enabled and self.pitch_slider.value() != self.PITCH_DEFAULT)
		self.pitch_slider.setEnabled(enabled)
		self.main_btn.setEnabled(enabled)
		self.sync_btn.setEnabled(enabled)
		self.tempo_label.setEnabled(enabled)
		self.tempo_value_label.setEnabled(enabled)

	def set_speed(self, value: int):
		# Convert integer slider (-100..100) to float -1..1, then to log range 0.5..2.0
		# 2^x maps (-1, 0, 1) -> (0.5, 1.0, 2.0)
		x = value / 100.0
		speed = 2 ** x
		self.command_util.send_command({"command": "set_speed", "speed": speed})
		self._update_tempo_display()

	def _update_tempo_display(self):
		"""Display tempo = original tempo scaled by current speed ratio."""
		if self._original_tempo is None:
			self.tempo_value_label.setText("---.-")
			if self._on_effective_tempo_changed:
				self._on_effective_tempo_changed(None)
			return
		speed = 2 ** (self.speed_slider.value() / 100.0)
		effective_tempo = self._original_tempo * speed
		self.tempo_value_label.setText(f"{effective_tempo:03.1f}")
		if self._on_effective_tempo_changed:
			self._on_effective_tempo_changed(effective_tempo)

	def get_effective_tempo(self) -> float | None:
		"""Current playback tempo (original * speed ratio)."""
		if self._original_tempo is None:
			return None
		speed = 2 ** (self.speed_slider.value() / 100.0)
		return self._original_tempo * speed

	def set_pitch(self, value: int):
		pitch = value / 100.0
		self.command_util.send_command({"command": "set_pitch", "pitch": pitch})

	def set_tempo(self, tempo: float):
		"""Set original tempo (from file analysis). Display shows original * speed ratio."""
		self._original_tempo = max(0, tempo)
		self._update_tempo_display()
