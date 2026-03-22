from audioBuffer import AudioBuffer
import numpy as np
from commandUtil import CommandUtil
# Audio Track class
# Has stateful position and playing flag
# For now the entire thing has a single buffer in memory,
# but in theory that could be chunked out into multiple buffers

# Linear interpolation is superior, but more expensive. Default to nearest-neighbor.
USE_LINEAR_INTERPOLATION = True

class AudioTrack:
	def __init__(self, buffer: AudioBuffer | None = None, command_util: CommandUtil | None = None):
		self.position = 0
		self.playing = False
		self.looping = False
		self.command_util = command_util
		self.speed = 1.0
		self.set_buffer(buffer)

	def set_buffer(self, buffer: AudioBuffer):
		self.buffer = buffer
		self.duration = buffer.sample_len / 44100
		if (self.position > self.duration):
			self.position = 0

	def seek(self, position: float):
		self.position = max(0, min(position, self.duration))

	def set_speed(self, speed: float):
		self.speed = speed

	# If track is paused we provide zeros, otherwise we provide samples from the track and advance position accordingly.
	# When we reach the end of the buffer, we loop back to the start.
	def get_samples(self, frame_count: int) -> np.ndarray:
		if not self.playing or self.buffer is None or self.buffer.sample_len == 0:
			return np.zeros(frame_count * 2, dtype=np.float32)

		buffer = self.buffer.buffer

		start_frame = int(self.position * 44100) % self.buffer.sample_len

		# Starting here, we need to scale requested output frames by playback speed
		frames_until_end = int((self.buffer.sample_len - start_frame) * self.speed)
		scaled_frame_count = int(frame_count * self.speed)

		if scaled_frame_count <= frames_until_end:
			original_stereo = buffer[start_frame * 2 : (start_frame + scaled_frame_count) * 2].copy()
			left = original_stereo[0::2]
			right = original_stereo[1::2]
			scaled_stereo = np.empty(frame_count * 2, dtype=np.float32)
			if USE_LINEAR_INTERPOLATION:
				sample_positions = np.linspace(0, scaled_frame_count - 1, frame_count, dtype=np.float32)
				xp = np.arange(scaled_frame_count, dtype=np.float32)
				scaled_stereo[0::2] = np.interp(sample_positions, xp, left)
				scaled_stereo[1::2] = np.interp(sample_positions, xp, right)
			else:
				# Nearest-neighbor interpolation
				indices = np.round(np.linspace(0, scaled_frame_count - 1, frame_count)).astype(np.intp)
				scaled_stereo[0::2] = left[indices]
				scaled_stereo[1::2] = right[indices]
			stereo = scaled_stereo
			source_frames_consumed = scaled_frame_count
		else:
			first_part = buffer[start_frame * 2 : (start_frame + frames_until_end) * 2]
			if self.looping:
				second_part = buffer[0 : (frame_count - frames_until_end) * 2]
			else:
				second_part = np.zeros((frame_count - frames_until_end) * 2, dtype=np.float32)
			stereo = np.concatenate([first_part, second_part])
			source_frames_consumed = frames_until_end + (frame_count - frames_until_end)

		self.position += source_frames_consumed / 44100
		if self.position >= self.duration:
			if self.looping:
				self.position = self.position % self.duration
			else:
				self.position = 0
				self.playing = False
				self.command_util.send_status({"type": "track_stopped"})
		return stereo
