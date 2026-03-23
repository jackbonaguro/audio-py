from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QSlider
from PySide6.QtCore import Qt

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
		self.pitch_slider.setRange(-12, 12)
		self.pitch_slider.setValue(0)
		self.pitch_slider.valueChanged.connect(self.set_pitch)
		self.pitch_slider.setTickPosition(QSlider.TickPosition.TicksBelow)
		self.pitch_slider.setTickInterval(1)
		self.addWidget(self.pitch_label)
		self.addWidget(self.pitch_slider)

		# Master and Sync buttons (no behavior yet)
		self.master_btn = QPushButton("Master")
		self.sync_btn = QPushButton("Sync")
		self.addWidget(self.master_btn)
		self.addWidget(self.sync_btn)

	def set_speed(self, value: int):
		# Convert integer slider (-100..100) to float -1..1, then to log range 0.5..2.0
		# 2^x maps (-1, 0, 1) -> (0.5, 1.0, 2.0)
		x = value / 100.0
		speed = 2 ** x
		self.command_util.send_command({"command": "set_speed", "speed": speed})

	def set_pitch(self, value: int):
		self.command_util.send_command({"command": "set_pitch", "pitch": value})
