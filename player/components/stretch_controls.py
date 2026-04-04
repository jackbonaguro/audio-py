import math
from typing import Callable

from PySide6.QtWidgets import QHBoxLayout, QPushButton, QSlider

from PySide6.QtCore import Qt

from commandUtil import CommandUtil

from .label_value import LabelValuePair


class StretchControls(QHBoxLayout):
	def __init__(
		self,
		command_util: CommandUtil,
		track_id: int,
		app_state,
		on_main_track_changed: Callable[[], None],
		on_effective_tempo_changed: Callable[[float | None], None] | None = None,
		on_sync_changed: Callable[[], None] | None = None,
	):
		super().__init__()
		self.command_util = command_util
		self._track_id = track_id
		self._app_state = app_state
		self._on_main_track_changed = on_main_track_changed
		self._on_effective_tempo_changed = on_effective_tempo_changed
		self._on_sync_changed = on_sync_changed
		self._original_tempo: float | None = None
		# Last speed ratio sent to RT (0.5–2.0). Slider is quantized; this is authoritative for tempo math.
		self._speed_ratio = 1.0

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
		self.sync_btn.setToolTip("Sync tempo to main track")
		self.sync_btn.setCheckable(True)
		self.sync_btn.clicked.connect(self._on_sync_clicked)
		self.addWidget(self.main_btn)
		self.addWidget(self.sync_btn)

		self.tempo_pair = LabelValuePair("Tempo: ", ["---.-", "999.9"])
		self.addWidget(self.tempo_pair)

	SPEED_DEFAULT = 0
	PITCH_DEFAULT = 0

	def _reset_speed(self):
		self.speed_slider.setValue(self.SPEED_DEFAULT)

	def _reset_pitch(self):
		self.pitch_slider.setValue(self.PITCH_DEFAULT)

	def _update_speed_reset_btn(self):
		if self._track_id not in self._app_state.synced_tracks:
			self.speed_reset_btn.setEnabled(self.speed_slider.value() != self.SPEED_DEFAULT)

	def _on_sync_clicked(self):
		if self._track_id in self._app_state.synced_tracks:
			self._app_state.synced_tracks.discard(self._track_id)
			self.sync_btn.setChecked(False)
		else:
			# Sync: set our effective tempo to main tempo
			if (
				self._app_state.main_tempo is not None
				and self._original_tempo is not None
				and self._original_tempo > 0
			):
				self._app_state.synced_tracks.add(self._track_id)
				self.sync_btn.setChecked(True)
				self.set_effective_tempo(self._app_state.main_tempo)
				self._update_speed_controls_enabled(True)
		if self._on_sync_changed:
			self._on_sync_changed()

	def set_sync_state(self, is_synced: bool):
		self.sync_btn.setChecked(is_synced)

	def set_effective_tempo(self, target_tempo: float):
		"""Set speed so effective tempo equals target_tempo. Used when synced."""
		if self._original_tempo is None or self._original_tempo <= 0:
			return
		# Exact ratio; do not round-trip through the slider for audio or tempo math.
		self._speed_ratio = max(0.5, min(2.0, target_tempo / self._original_tempo))
		slider_value = int(round(100 * math.log2(self._speed_ratio)))
		slider_value = max(-100, min(100, slider_value))
		self.speed_slider.blockSignals(True)
		self.speed_slider.setValue(slider_value)
		self.speed_slider.blockSignals(False)
		self.command_util.send_command({"command": "set_speed", "speed": self._speed_ratio})
		self._update_tempo_display()

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
		self._update_speed_controls_enabled(enabled)
		self.pitch_reset_btn.setEnabled(enabled and self.pitch_slider.value() != self.PITCH_DEFAULT)
		self.pitch_slider.setEnabled(enabled)
		self.main_btn.setEnabled(enabled)
		self._update_sync_btn_enabled(enabled)
		self.tempo_pair.set_enabled(enabled)

	def _update_speed_controls_enabled(self, base_enabled: bool):
		"""Speed controls disabled when synced (tempo driven by main)."""
		is_synced = self._track_id in self._app_state.synced_tracks
		slider_enabled = base_enabled and not is_synced
		self.speed_slider.setEnabled(slider_enabled)
		self.speed_reset_btn.setEnabled(
			slider_enabled and self.speed_slider.value() != self.SPEED_DEFAULT
		)

	def _update_sync_btn_enabled(self, base_enabled: bool):
		"""Sync available when: has file, has main track with tempo, and not the main track."""
		can_sync = (
			base_enabled
			and self._app_state.main_track is not None
			and self._app_state.main_tempo is not None
			and self._app_state.main_track != self._track_id
			and self._original_tempo is not None
			and self._original_tempo > 0
		)
		self.sync_btn.setEnabled(can_sync)

	def set_speed(self, value: int):
		# Convert integer slider (-100..100) to float -1..1, then to log range 0.5..2.0
		# 2^x maps (-1, 0, 1) -> (0.5, 1.0, 2.0)
		x = value / 100.0
		self._speed_ratio = 2 ** x
		self.command_util.send_command({"command": "set_speed", "speed": self._speed_ratio})
		self._update_tempo_display()

	def _update_tempo_display(self):
		"""Display tempo = original tempo scaled by current speed ratio."""
		if self._original_tempo is None:
			self.tempo_pair.set_text("---.-")
			if self._on_effective_tempo_changed:
				self._on_effective_tempo_changed(None)
			return
		effective_tempo = self._original_tempo * self._speed_ratio
		self.tempo_pair.set_text(f"{effective_tempo:03.1f}")
		if self._on_effective_tempo_changed:
			self._on_effective_tempo_changed(effective_tempo)

	def get_effective_tempo(self) -> float | None:
		"""Current playback tempo (original * speed ratio)."""
		if self._original_tempo is None:
			return None
		return self._original_tempo * self._speed_ratio

	def set_pitch(self, value: int):
		pitch = value / 100.0
		self.command_util.send_command({"command": "set_pitch", "pitch": pitch})

	def set_tempo(self, tempo: float):
		"""Set original tempo (from file analysis). Display shows original * speed ratio."""
		self._original_tempo = max(0, tempo)
		self._speed_ratio = 1.0
		self.speed_slider.blockSignals(True)
		self.speed_slider.setValue(self.SPEED_DEFAULT)
		self.speed_slider.blockSignals(False)
		self._update_tempo_display()
