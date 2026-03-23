from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QSlider
from PySide6.QtCore import Qt
from PySide6.QtGui import QFontDatabase, QFontMetrics

from commandUtil import CommandUtil


class SpeedPitchSection(QHBoxLayout):
	def __init__(self, command_util: CommandUtil):
		super().__init__()
		self.command_util = command_util

		# Logarithmic playback speed adjust slider
		self.speed_label = QLabel("Speed")
		self.speed_slider = QSlider(Qt.Orientation.Horizontal)
		self.speed_slider.setRange(-100, 100)
		self.speed_slider.setValue(0)
		self.speed_slider.valueChanged.connect(self.set_speed)
		self.speed_slider.setTickPosition(QSlider.TickPosition.TicksBelow)
		self.speed_slider.setTickInterval(10)
		self.addWidget(self.speed_label)
		self.addWidget(self.speed_slider)

		# Pitch adjust slider
		self.pitch_label = QLabel("Pitch")
		self.pitch_slider = QSlider(Qt.Orientation.Horizontal)
		self.pitch_slider.setRange(-1200, 1200)
		self.pitch_slider.setValue(0)
		self.pitch_slider.setTickInterval(100)
		self.pitch_slider.setTickPosition(QSlider.TickPosition.TicksBelow)
		self.pitch_slider.valueChanged.connect(self.set_pitch)
		self.addWidget(self.pitch_label)
		self.addWidget(self.pitch_slider)

		# Master and Sync buttons (no behavior yet)
		self.master_btn = QPushButton("Main")
		self.sync_btn = QPushButton("Sync")
		self.reset_btn = QPushButton("Reset")
		self.addWidget(self.master_btn)
		self.addWidget(self.sync_btn)
		self.addWidget(self.reset_btn)

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

	def set_speed(self, value: int):
		# Convert integer slider (-100..100) to float -1..1, then to log range 0.5..2.0
		# 2^x maps (-1, 0, 1) -> (0.5, 1.0, 2.0)
		x = value / 100.0
		speed = 2 ** x
		self.command_util.send_command({"command": "set_speed", "speed": speed})

	def set_pitch(self, value: int):
		pitch = value / 100.0
		self.command_util.send_command({"command": "set_pitch", "pitch": pitch})

	def set_tempo(self, tempo: float):
		self.tempo = max(0, tempo)
		self.tempo_value_label.setText(f"{tempo:03.1f}")
