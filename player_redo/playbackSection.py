from PySide6.QtWidgets import QHBoxLayout, QPushButton

from commandUtil import CommandUtil

class PlaybackSection(QHBoxLayout):
	def __init__(self, command_util: CommandUtil):
		super().__init__()

		self.command_util = command_util

		self.play_btn = QPushButton("Play")
		self.play_btn.clicked.connect(self.play)
		self.play_btn.setEnabled(False)
		self.addWidget(self.play_btn)

		self.pause_btn = QPushButton("Pause")
		self.pause_btn.clicked.connect(self.pause)
		self.pause_btn.setEnabled(False)
		self.addWidget(self.pause_btn)

		self.stop_btn = QPushButton("Stop")
		self.stop_btn.clicked.connect(self.stop)
		self.stop_btn.setEnabled(False)
		self.addWidget(self.stop_btn)

	def set_enabled(self, enabled: bool):
		self.play_btn.setEnabled(enabled)

	def play(self):
		self.command_util.send_command({"command": "play"})
		self.play_btn.setEnabled(False)
		self.pause_btn.setEnabled(True)
		self.stop_btn.setEnabled(True)

	def pause(self):
		self.command_util.send_command({"command": "pause"})
		self.play_btn.setEnabled(True)
		self.pause_btn.setEnabled(False)
		self.stop_btn.setEnabled(True)

	def stop(self):
		self.command_util.send_command({"command": "stop"})
		self.play_btn.setEnabled(True)
		self.pause_btn.setEnabled(False)
		self.stop_btn.setEnabled(False)
