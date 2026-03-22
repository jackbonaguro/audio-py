import multiprocessing as mp
import threading
import time

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QThread, QCoreApplication, Signal
from gui import MainWindow
from engine import AudioEngine

from commandUtil import CommandUtil

def realtime_worker(cmd_q: mp.Queue, status_q: mp.Queue):
	import gc
	gc.disable()  # Prevent GC pauses from causing buffer underruns (pops)

	command_util = CommandUtil(cmd_q, status_q)
	import os
	try:
		os.nice(-10)  # Higher priority
	except (PermissionError, AttributeError):
		pass
	
	# Qt event loop required for LoadWorker signals to be delivered to engine slots
	app = QCoreApplication([])

	engine = AudioEngine(command_util)

	def on_position_update(position: float):
		try:
			status_q.put_nowait({"type": "position", "position": position})
		except mp.queues.Full:
			pass

	engine.set_on_position_update(on_position_update)

	state = {"running": True}

	def command_listener():
		while state["running"]:
			try:
				cmd = cmd_q.get_nowait()
				if cmd.get("command") == "quit":
					state["running"] = False
					app.quit()
				elif cmd.get("command") == "stop":
					engine.stop_track()
				elif cmd.get("command") == "play":
					engine.play_track()
				elif cmd.get("command") == "pause":
					engine.pause_track()
				elif cmd.get("command") == "load_file":
					path = cmd.get("path")
					if path:
						engine.load_file(path)
				elif cmd.get("command") == "seek":
					pos = cmd.get("position")
					if pos is not None:
						engine.seek_track(float(pos))
				elif cmd.get("command") == "set_speed":
					speed = cmd.get("speed")
					if speed is not None:
						engine.set_track_speed(float(speed))
			except mp.queues.Empty:
				pass

			# Avoid burning CPU when queue is empty.
			time.sleep(0.01)

	# Start command listener thread
	listener = threading.Thread(target=command_listener, daemon=True)
	listener.start()

	app.exec()

class GuiQThread(QThread):
	waveform_ready = Signal(object)
	load_progress = Signal(float)
	position_received = Signal(float)
	track_stopped = Signal()

	def __init__(self, command_util: CommandUtil, main_window: MainWindow):
		super().__init__()
		self.command_util = command_util
		self.main_window = main_window

	def run(self):
		while True:
			try:
				status = self.command_util.status_queue.get(timeout=0.1)
				type = status.get("type")
				if type == "position":
					self.position_received.emit(status.get("position"))
				if type == "load_progress":
					self.load_progress.emit(status.get("progress"))
				if type == "load_status":
					self.waveform_ready.emit(status)
				if type == "track_stopped":
					self.track_stopped.emit()
			except Exception:
				pass

def gui_worker(cmd_q: mp.Queue, status_q: mp.Queue):
	# Setup
	command_util = CommandUtil(cmd_q, status_q)
	app = QApplication([])
	window = MainWindow(command_util=command_util)

	# Unlike the realtime worker, we have Qt here for threads
	gui_thread = GuiQThread(command_util, window)
	gui_thread.waveform_ready.connect(window.on_waveform_ready)
	gui_thread.load_progress.connect(window.on_load_progress)
	gui_thread.position_received.connect(window.on_position_received)
	gui_thread.track_stopped.connect(window.on_track_stopped)
	gui_thread.start()

	window.show()
	app.exec()
	command_util.send_command({"command": "quit"})

if __name__ == "__main__":
	mp.set_start_method("spawn")  # Use spawn for cross-platform
	
	cmd_q = mp.Queue(maxsize=64)
	status_q = mp.Queue(maxsize=256)
	
	rt = mp.Process(target=realtime_worker, args=(cmd_q, status_q), daemon=True)
	rt.start()
	
	gui_worker(cmd_q, status_q)
	rt.join()
