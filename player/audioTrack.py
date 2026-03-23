from audioBuffer import AudioBuffer
import numpy as np
from commandUtil import CommandUtil

from sources.raw_data_source import RawDataSource
from sources.stretched_source import StretchedSource
from sources.audio_source import AudioSource

# Audio Track class
# Has stateful position and playing flag
# For now the entire thing has a single buffer in memory,
# but in theory that could be chunked out into multiple buffers


class AudioTrack:
	def __init__(
		self,
		buffer: AudioBuffer | None = None,
		command_util: CommandUtil | None = None,
	):
		self.reset()
		self.command_util = command_util
		self.set_buffer(buffer)

	def reset(self):
		self.position = 0
		self.playing = False
		self.looping = False
		self.speed = 1.0
		self.pitch_semitones = 0.0

	SAMPLE_RATE = 44100

	def set_buffer(self, buffer: AudioBuffer):
		"""For now, assume 2 stereo channels."""
		self.channel_count = 2

		self.channels = np.zeros((self.channel_count, buffer.sample_len), dtype=np.float32)
		self.channels[0] = buffer.buffer[0::2]
		self.channels[1] = buffer.buffer[1::2]

		self.total_frames = buffer.sample_len
		self.duration = buffer.sample_len / self.SAMPLE_RATE
		if self.position >= self.total_frames:
			self.position = 0

		self.raw_left = RawDataSource(self.channels[0])
		self.raw_right = RawDataSource(self.channels[1])
		time_ratio = 1.0 / self.speed
		pitch_scale = 2.0 ** (self.pitch_semitones / 12.0)
		self.stretched_left = StretchedSource(
			self.SAMPLE_RATE, time_ratio, pitch_scale, self.raw_left
		)
		self.stretched_right = StretchedSource(
			self.SAMPLE_RATE, time_ratio, pitch_scale, self.raw_right
		)
		self.source_left = self.stretched_left
		self.source_right = self.stretched_right

	def seek(self, position_seconds: float):
		"""Seek to position in seconds."""
		pos_frames = int(position_seconds * self.SAMPLE_RATE)
		self.position = max(0, min(pos_frames, self.total_frames))
		# Must seek through full chain: StretchedSource resets rubberband state.
		self.source_left.seek(self.position)
		self.source_right.seek(self.position)

	def set_speed(self, speed: float):
		"""Update playback speed. Real-time safe."""
		self.speed = speed
		time_ratio = 1.0 / speed
		self.stretched_left.set_time_ratio(time_ratio)
		self.stretched_right.set_time_ratio(time_ratio)

	def set_pitch(self, pitch_semitones: float):
		"""Set pitch in semitones (-12 to 12). 0 = no change, 12 = one octave up. Real-time safe."""
		self.pitch_semitones = pitch_semitones
		self.stretched_left.set_pitch_semitones(pitch_semitones)
		self.stretched_right.set_pitch_semitones(pitch_semitones)

	# If track is paused we provide zeros, otherwise we provide samples from the track and advance position accordingly.
	# When we reach the end of the buffer, we loop back to the start.
	def get_samples(self, frame_count: int) -> np.ndarray:
		if not self.playing or self.channel_count == 0 or self.duration == 0:
			return np.zeros(frame_count * 2, dtype=np.float32)

		frames_until_end = self.total_frames - self.position

		stereo = np.zeros(frame_count * 2, dtype=np.float32)
		if frame_count <= frames_until_end:
			frames_left, _ = self.source_left.pull(frame_count)
			frames_right, _ = self.source_right.pull(frame_count)
			n_out = min(len(frames_left), len(frames_right), frame_count)
			if n_out > 0:
				stereo[: n_out * 2 : 2] = frames_left[:n_out]
				stereo[1 : n_out * 2 : 2] = frames_right[:n_out]
		else:
			first_part_left, _ = self.source_left.pull(frames_until_end)
			first_part_right, _ = self.source_right.pull(frames_until_end)
			remaining_frames = frame_count - frames_until_end
			second_part_left = np.zeros(remaining_frames, dtype=np.float32)
			second_part_right = np.zeros(remaining_frames, dtype=np.float32)

			if self.looping:
				# If looping fill from beginning. Otherwise it's already filled with zeros.
				second_part_left, _ = self.source_left.pull(remaining_frames)
				second_part_right, _ = self.source_right.pull(remaining_frames)

			left = np.concatenate([first_part_left, second_part_left[:remaining_frames]])
			right = np.concatenate([first_part_right, second_part_right[:remaining_frames]])
			n_out = min(len(left), len(right), frame_count)
			if n_out > 0:
				stereo[: n_out * 2 : 2] = left[:n_out]
				stereo[1 : n_out * 2 : 2] = right[:n_out]

		# Advance by actual source frames consumed (output_frames * speed)
		self.position += int(frame_count * self.speed)
		if self.position >= self.total_frames:
			if self.looping:
				self.position = self.position % self.total_frames
				self.source_left.seek(self.position)
				self.source_right.seek(self.position)
			else:
				self.position = 0
				self.playing = False
				self.command_util.send_status({"type": "track_stopped"})
		return stereo
