import multiprocessing as mp
import sys
import threading
import time

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QThread, QCoreApplication, Signal
from gui import MainWindow
from engine import AudioEngine

from commandUtil import CommandUtil

def realtime_worker(cmd_q: mp.Queue, status_q: mp.Queue, log_q: mp.Queue):
	import gc
	import sys
	gc.disable()  # Prevent GC pauses from causing buffer underruns (pops)

	class QueueStdout:
		def __init__(self, queue):
			self.queue = queue
		def write(self, s):
			if s:
				try:
					self.queue.put_nowait(s)
				except mp.queues.Full:
					pass
		def flush(self):
			pass
	sys.stdout = QueueStdout(log_q)

	class QueueStderr:
		def __init__(self, queue):
			self.queue = queue
		def write(self, s):
			if s:
				try:
					self.queue.put_nowait(s)
				except mp.queues.Full:
					pass
		def flush(self):
			pass
	sys.stderr = QueueStderr(log_q)

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
						target = float(pos)
						deferred = []
						while True:
							# Don't directly pass seek commands, as there'll be too many to process in real time
							# Instead, gather all seek commands in the queue and seek to the last one
							try:
								c = cmd_q.get_nowait()
								if c.get("command") == "seek" and c.get("position") is not None:
									target = float(c["position"])
								else:
									deferred.append(c)
							except mp.queues.Empty:
								break
						engine.seek_track(target)
						for c in deferred:
							cmd_q.put(c)
				elif cmd.get("command") == "set_speed":
					speed = cmd.get("speed")
					if speed is not None:
						engine.set_track_speed(float(speed))
				elif cmd.get("command") == "set_pitch":
					pitch = cmd.get("pitch")
					if pitch is not None:
						engine.set_track_pitch(float(pitch))
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

def log_relay(log_q: mp.Queue, error_q: mp.Queue):
	while True:
		try:
			msg = log_q.get()
			if msg is None:
				break
			print(msg, end="", flush=True)
			# error_q is unused (realtime worker sends stderr to log_q); non-blocking check
			try:
				err = error_q.get_nowait()
				if err is not None:
					print(err, file=sys.stderr, end="", flush=True)
			except mp.queues.Empty:
				pass
		except Exception:
			break

if __name__ == "__main__":
	mp.set_start_method("spawn")  # Use spawn for cross-platform
	
	cmd_q = mp.Queue(maxsize=64)
	status_q = mp.Queue(maxsize=256)
	log_q = mp.Queue(maxsize=256)
	error_q = mp.Queue(maxsize=256)
	
	rt = mp.Process(target=realtime_worker, args=(cmd_q, status_q, log_q), daemon=True)
	rt.start()
	
	relay = threading.Thread(target=log_relay, args=(log_q, error_q), daemon=True)
	relay.start()
	
	gui_worker(cmd_q, status_q)
	log_q.put(None)
	error_q.put(None)
	rt.join()
