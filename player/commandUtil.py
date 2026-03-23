import multiprocessing as mp

class CommandUtil:
	def __init__(self, command_queue: mp.Queue, status_queue: mp.Queue):
		self.command_queue = command_queue
		self.status_queue = status_queue

	def send_command(self, command: dict):
		self.command_queue.put(command)
	
	def send_status(self, status: dict):
		self.status_queue.put(status)
