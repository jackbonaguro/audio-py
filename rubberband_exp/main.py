import rubberband
import soundfile
import pyaudio
import numpy as np
import time

# Global audio buffer and play position
audio_buffer = np.zeros((0, 2), dtype=np.float32)
play_position = 0

def main():
	global audio_buffer, play_position
	# Load file's data into numpy array
	audio, sample_rate = soundfile.read("./gravity.mp3")
	print(audio.shape)

	# Apply time stretch with ratio that produces inverted semitone repitch after resampling
	semitones = 3
	ratio = 2**(semitones/12)
	stretched_left = stretch_channel(audio[:, 0], ratio)
	stretched_right = stretch_channel(audio[:, 1], ratio)

	# Resample
	resampled_left = resample_channel(stretched_left, stretched_left.shape[0], audio.shape[0])
	resampled_right = resample_channel(stretched_right, stretched_right.shape[0], audio.shape[0])

	# Interleaved stereo: (N, 2) for L/R channels
	resampled_audio = np.column_stack([resampled_left, resampled_right])

	# Write to audio buffer and reset play position
	audio_buffer = resampled_audio
	play_position = 0

	# Create pyAudio stream
	pa = pyaudio.PyAudio()
	stream = pa.open(format=pyaudio.paFloat32, channels=2, rate=44100, output=True, stream_callback=stream_callback)
	stream.start_stream()

	# Wait for stream to finish
	while stream.is_active():
		time.sleep(0.1)

	stream.stop_stream()
	stream.close()
	pa.terminate()

def stretch_channel(channel: np.ndarray, ratio: float) -> np.ndarray:
	return rubberband.stretch(
		channel.astype(np.float32),
		rate=44100,
		ratio=ratio,
		crispness=5,
		formants=False,
		precise=True
	)

def resample_channel(channel: np.ndarray, source_frame_count: int, output_frame_count: int) -> np.ndarray:
	if source_frame_count == 0:
		return np.zeros(output_frame_count, dtype=np.float32)

	# Sample positions are the output frame indices
	sample_positions = np.linspace(
		0, source_frame_count - 1, output_frame_count, dtype=np.float32
	)
	# XP is the source frame indices
	xp = np.arange(source_frame_count, dtype=np.float32)
	return np.interp(sample_positions, xp, channel).astype(np.float32)

def stream_callback(in_data, frame_count, time_info, status):
	global audio_buffer, play_position
	# frame_count frames = frame_count rows of (L, R)
	chunk = audio_buffer[play_position:play_position + frame_count]
	play_position += len(chunk)
	if len(chunk) < frame_count:
		# Pad with zeros and signal completion
		padded = np.zeros((frame_count, 2), dtype=np.float32)
		padded[:len(chunk)] = chunk
		return (padded.tobytes(), pyaudio.paComplete)
	return (chunk.tobytes(), pyaudio.paContinue)


if __name__ == "__main__":
	main()
