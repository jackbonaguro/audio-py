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
	
	app = QCoreApplication([])

	engine = AudioEngine(command_util)

	def on_position_update(position: float, track_id: int):
		try:
			status_q.put_nowait({"type": "position", "position": position, "track_id": track_id})
		except mp.queues.Full:
			pass

	engine.set_on_position_update(on_position_update)

	state = {"running": True}

	# Operation -> value param (same name ensures command and value stay in sync)
	_DRAIN_OPS = {"seek": "position", "set_speed": "speed", "set_pitch": "pitch"}

	def drain_and_apply(operation: str, apply_fn, group_by: str | None = None, initial_cmd=None):
		"""Drain matching commands from queue, apply last value per group. Re-queue other commands.
		operation identifies the command type and value param (e.g. set_speed -> extracts "speed").
		group_by: param to group by for uniqueness (e.g. track_id); apply_fn(group_key, value) per group.
		initial_cmd: already-consumed first command to include."""
		value_param = _DRAIN_OPS.get(operation)
		if value_param is None:
			return
		deferred = []
		merged = {}
		if initial_cmd is not None and initial_cmd.get("command") == operation and initial_cmd.get(value_param) is not None:
			k = initial_cmd.get(group_by) if group_by else None
			if group_by is None or k is not None:
				merged[k] = float(initial_cmd[value_param])
		while True:
			try:
				c = cmd_q.get_nowait()
				if c.get("command") == operation and c.get(value_param) is not None:
					k = c.get(group_by) if group_by else None
					if group_by is None or k is not None:
						merged[k] = float(c[value_param])
				else:
					deferred.append(c)
			except mp.queues.Empty:
				break
		for k, value in merged.items():
			if group_by is not None:
				apply_fn(k, value)
			else:
				apply_fn(value)
		for c in deferred:
			cmd_q.put(c)

	def command_listener():
		while state["running"]:
			try:
				cmd = cmd_q.get_nowait()
				if cmd.get("command") == "quit":
					state["running"] = False
					# Clean up shared memory before exit to avoid resource_tracker warnings
					if engine._current_shm is not None:
						try:
							engine.tracks.clear()
							engine._current_shm.close()
							engine._current_shm.unlink()
						except Exception:
							pass
						engine._current_shm = None
					app.quit()
				elif cmd.get("command") == "stop":
					engine.stop_track(cmd.get("track_id"))
				elif cmd.get("command") == "play":
					engine.play_track(cmd.get("track_id"))
				elif cmd.get("command") == "pause":
					engine.pause_track(cmd.get("track_id"))
				elif cmd.get("command") == "track_ready":
					shm_name = cmd.get("shm_name")
					sample_len = cmd.get("sample_len")
					track_id = cmd.get("track_id")
					if shm_name is not None and sample_len is not None and track_id is not None:
						engine.load_from_shared_memory(shm_name, sample_len, track_id)
				elif cmd.get("command") == "seek":
					drain_and_apply(
						"seek",
						lambda track_id, position: engine.seek_track(track_id, position),
						group_by="track_id", initial_cmd=cmd,
					)
				elif cmd.get("command") == "set_speed":
					drain_and_apply(
						"set_speed",
						lambda track_id, speed: engine.set_track_speed(track_id, speed),
						group_by="track_id", initial_cmd=cmd,
					)
				elif cmd.get("command") == "set_pitch":
					drain_and_apply(
						"set_pitch",
						lambda track_id, pitch: engine.set_track_pitch(track_id, pitch),
						group_by="track_id", initial_cmd=cmd,
					)
			except mp.queues.Empty:
				pass

			# Avoid burning CPU when queue is empty.
			time.sleep(0.01)

	# Start command listener thread
	listener = threading.Thread(target=command_listener, daemon=True)
	listener.start()

	app.exec()

_SHUTDOWN_SENTINEL = "_shutdown"  # Picklable sentinel for GuiQThread


class GuiQThread(QThread):
	waveform_ready = Signal(object)
	load_progress = Signal(float)
	position_received = Signal(object)  # status dict: {position, track_id?}
	track_stopped = Signal(object)      # status dict: {track_id?}

	def __init__(self, command_util: CommandUtil, main_window: MainWindow):
		super().__init__()
		self.command_util = command_util
		self.main_window = main_window

	def run(self):
		while True:
			try:
				status = self.command_util.status_queue.get(timeout=0.1)
				if status == _SHUTDOWN_SENTINEL:
					return
				type = status.get("type")
				if type == "position":
					self.position_received.emit(status)
				if type == "load_progress":
					self.load_progress.emit(status.get("progress"))
				if type == "load_status":
					self.waveform_ready.emit(status)
				if type == "track_stopped":
					self.track_stopped.emit(status)
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
	# Stop GuiQThread cleanly before quitting RT process
	command_util.status_queue.put(_SHUTDOWN_SENTINEL)
	gui_thread.wait(2000)
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
